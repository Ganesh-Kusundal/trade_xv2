"""SessionManager — connection lifecycle for broker stream sessions.

Owns the open / close / reuse lifecycle of every ``StreamSession``.
Each session is tracked with its ``BrokerStreamHandle``, raw-frame callback,
and associated reconnect monitor task.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from domain.ports.broker_gateway import BrokerStreamPlan
from domain.ports.time_service import get_current_clock
from domain.stream_health import (
    StreamHealth,
    StreamSession,
    SubscriptionState,
    TransportState,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage stream-session open, disconnect, and instrument merging.

    Parameters
    ----------
    registry : BrokerRegistry
        Used to look up broker gateways.
    sessions : dict[str, StreamSession]
        Shared reference — orchestrator owns the dict.
    handles : dict[str, BrokerStreamHandle]
        Shared reference — handles keyed by session_id.
    frame_handlers : dict[str, Any]
        Shared reference — on_raw_frame callbacks keyed by session_id.
    reconnect_tasks : dict[str, asyncio.Task]
        Shared reference — reconnect monitor tasks keyed by session_id.
    tasks : list[asyncio.Task]
        Shared reference — orchestrator's task list for lifecycle management.
    lock : asyncio.Lock
        Shared lock for thread-safe access to shared dicts.
    make_frame_callback : Callable[[str, str], Callable]
        Factory that returns a ``on_raw_frame`` closure bridging to the
        tick router.  Orchestrator provides this.
    log_state_change : Callable
        Called on every transport/subscription/freshness transition.
    """

    def __init__(
        self,
        registry,
        sessions,
        handles,
        frame_handlers,
        reconnect_tasks,
        tasks,
        lock: asyncio.Lock,
        make_frame_callback,
        log_state_change,
    ) -> None:
        self._registry = registry
        self._sessions = sessions
        self._handles = handles
        self._frame_handlers = frame_handlers
        self._reconnect_tasks = reconnect_tasks
        self._tasks = tasks
        self._lock = lock
        self._make_frame_callback = make_frame_callback
        self._log_state_change = log_state_change

    # ------------------------------------------------------------------
    # Open
    # ------------------------------------------------------------------

    async def open_session(
        self,
        broker_id: str,
        request,
        trace_id: str,
        *,
        reconnect_coro,
    ) -> str:
        """Open a new stream session.  Called with ``_lock`` held."""
        session_id = str(uuid.uuid4())
        session = StreamSession(
            session_id=session_id,
            broker_id=broker_id,
            stream_kind=request.stream_kind,
            instruments=request.instruments,
            modes=request.modes,
            health=StreamHealth(stale_seconds_threshold=request.freshness_sla_s),
            created_at=get_current_clock().now(),
        )
        session.update_transport(TransportState.CONNECTING)
        self._sessions[session_id] = session
        self._log_state_change(session_id, "NONE", TransportState.CONNECTING.value, "open_session")

        gw = self._registry.get_gateway(broker_id)

        on_raw_frame = self._make_frame_callback(session_id, request.stream_kind)
        self._frame_handlers[session_id] = on_raw_frame

        plan = BrokerStreamPlan(
            instruments=request.instruments,
            modes=request.modes,
            on_raw_frame=on_raw_frame,
        )

        try:
            if request.stream_kind == "market":
                handle = await gw.open_market_stream(plan)
            else:
                handle = await gw.open_order_stream(plan)
            self._handles[session_id] = handle
            session.update_transport(TransportState.CONNECTED)
            session.update_subscription(SubscriptionState.ACKNOWLEDGED)
            self._log_state_change(
                session_id,
                TransportState.CONNECTING.value,
                TransportState.CONNECTED.value,
                "session_opened",
            )
        except Exception as exc:
            session.update_transport(TransportState.DISCONNECTED)
            self._log_state_change(
                session_id,
                TransportState.CONNECTING.value,
                TransportState.DISCONNECTED.value,
                f"open_failed:{exc}",
            )
            raise

        # Spawn a reconnect monitor for this session
        reconnect_task = asyncio.create_task(
            reconnect_coro(session_id, request),
            name=f"stream.reconnect.{session_id[:8]}",
        )
        self._reconnect_tasks[session_id] = reconnect_task
        self._tasks.append(reconnect_task)
        return session_id

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    async def disconnect_session(self, session_id: str, reason: str = "") -> None:
        """Disconnect and clean up a session."""
        reconnect_task = self._reconnect_tasks.pop(session_id, None)
        if reconnect_task is not None:
            reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reconnect_task
            if reconnect_task in self._tasks:
                self._tasks.remove(reconnect_task)

        self._frame_handlers.pop(session_id, None)
        handle = self._handles.pop(session_id, None)
        session = self._sessions.pop(session_id, None)
        if handle:
            with contextlib.suppress(Exception):
                await handle.disconnect()
        if session:
            self._log_state_change(
                session_id,
                session.health.transport.value,
                TransportState.DISCONNECTED.value,
                reason,
            )

    # ------------------------------------------------------------------
    # Reuse
    # ------------------------------------------------------------------

    def find_reusable_session(self, broker_id: str, request) -> StreamSession | None:
        """Return an existing healthy session for the same broker and stream kind."""
        for session in self._sessions.values():
            if (
                session.broker_id == broker_id
                and session.stream_kind == request.stream_kind
                and session.is_healthy()
            ):
                return session
        return None

    async def merge_instruments(self, session: StreamSession, request) -> None:
        """Subscribe any new instruments when reusing an existing session."""
        new_instruments = request.instruments - session.instruments
        if not new_instruments:
            return
        session.instruments = session.instruments | request.instruments
        if request.modes:
            session.modes = session.modes | request.modes

        gw = self._registry.get_gateway(session.broker_id)
        frame_cb = self._frame_handlers.get(session.session_id)
        plan = BrokerStreamPlan(
            instruments=new_instruments,
            modes=request.modes or session.modes,
            on_raw_frame=frame_cb,
        )
        if session.stream_kind == "market":
            await gw.open_market_stream(plan)
        else:
            await gw.open_order_stream(plan)
        session.update_subscription(SubscriptionState.ACKNOWLEDGED)
