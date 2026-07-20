"""ReconnectController — reconnect loop, cross-broker failover, heartbeat.

Monitors session transport health, drives exponential-backoff reconnect,
escalates to failover when all attempts on the current broker are exhausted,
and detects stale sessions via periodic heartbeat.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from domain.models.routing import OperationKind, RoutingRequest
from domain.ports.broker_gateway import BrokerStreamPlan
from domain.ports.time_service import get_current_clock
from domain.stream_health import (
    FreshnessState,
    SubscriptionState,
    TransportState,
)

logger = logging.getLogger(__name__)


class ReconnectController:
    """Reconnect, failover, and staleness detection for stream sessions.

    Parameters
    ----------
    registry : BrokerRegistry
        Gateway lookup.
    router : BrokerRouter
        Routing decisions for failover.
    sessions : dict[str, StreamSession]
        Shared reference — orchestrator owns the dict.
    handles : dict[str, BrokerStreamHandle]
        Shared reference.
    frame_handlers : dict[str, Any]
        Shared reference.
    lock : asyncio.Lock
        Shared lock.
    running : property / callable returning bool
        Whether the orchestrator is running.
    tasks : list[asyncio.Task]
        Shared reference — heartbeat task is appended here.
    log_state_change : Callable
    notify_health_change : Callable
    """

    _HEARTBEAT_INTERVAL_S = 5.0
    _RECONNECT_BASE_DELAY_S = 1.0
    _RECONNECT_MAX_DELAY_S = 60.0
    _MAX_RECONNECT_ATTEMPTS = 5

    def __init__(
        self,
        registry,
        router,
        sessions,
        handles,
        frame_handlers,
        lock: asyncio.Lock,
        running,
        tasks,
        log_state_change,
        notify_health_change,
    ) -> None:
        self._registry = registry
        self._router = router
        self._sessions = sessions
        self._handles = handles
        self._frame_handlers = frame_handlers
        self._lock = lock
        self._running = running
        self._tasks = tasks
        self._log_state_change = log_state_change
        self._notify_health_change = notify_health_change

    async def _disconnect_handle(self, session_id: str) -> None:
        """Close prior transport before reopen — prevents overlapping duplicate ticks."""
        old = self._handles.get(session_id)
        if old is None:
            return
        try:
            await old.disconnect()
        except Exception as exc:
            logger.debug("reconnect_disconnect_failed session=%s: %s", session_id, exc)
        async with self._lock:
            if self._handles.get(session_id) is old:
                del self._handles[session_id]

    # ------------------------------------------------------------------
    # Reconnect loop
    # ------------------------------------------------------------------

    async def reconnect_loop(self, session_id: str, original_request) -> None:
        """Monitor a session and reconnect on transport loss.

        After ``_MAX_RECONNECT_ATTEMPTS`` failures on the same broker,
        attempts cross-broker failover if allowed.
        """
        delay = self._RECONNECT_BASE_DELAY_S
        while self._running():
            await asyncio.sleep(1.0)
            session = self._sessions.get(session_id)
            if session is None:
                return

            handle = self._handles.get(session_id)
            transport_ok = handle is not None and handle.is_connected()

            if not transport_ok:
                session.update_transport(TransportState.RECONNECTING)
                self._log_state_change(
                    session_id,
                    TransportState.CONNECTED.value,
                    TransportState.RECONNECTING.value,
                    "transport_loss",
                )
                session.increment_reconnect()
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._RECONNECT_MAX_DELAY_S)

                if (
                    session.reconnect_generation >= self._MAX_RECONNECT_ATTEMPTS
                    and original_request.allow_failover
                ):
                    failover_ok = await self._try_failover(session_id, session, original_request)
                    if failover_ok:
                        return

                try:
                    await self._disconnect_handle(session_id)
                    broker_id = session.broker_id
                    gw = self._registry.get_gateway(broker_id)
                    frame_cb = self._frame_handlers.get(session_id)
                    plan = BrokerStreamPlan(
                        instruments=session.instruments,
                        modes=session.modes,
                        on_raw_frame=frame_cb,
                    )
                    if session.stream_kind == "market":
                        handle = await gw.open_market_stream(plan)
                    else:
                        handle = await gw.open_order_stream(plan)

                    async with self._lock:
                        self._handles[session_id] = handle
                    session.update_transport(TransportState.CONNECTED)
                    session.update_subscription(SubscriptionState.ACKNOWLEDGED)
                    session.update_freshness(FreshnessState.UNKNOWN)
                    delay = self._RECONNECT_BASE_DELAY_S
                    self._log_state_change(
                        session_id,
                        TransportState.RECONNECTING.value,
                        TransportState.CONNECTED.value,
                        "reconnect_ok",
                    )
                except Exception as exc:
                    self._log_state_change(
                        session_id,
                        TransportState.RECONNECTING.value,
                        TransportState.RECONNECTING.value,
                        f"reconnect_failed:{exc}",
                    )

    # ------------------------------------------------------------------
    # Failover
    # ------------------------------------------------------------------

    async def _try_failover(self, session_id: str, session, original_request) -> bool:
        """Attempt to failover to a different broker.

        Returns True if failover succeeded, False if no fallback available.
        """
        current_broker = session.broker_id
        trace_id = str(uuid.uuid4())

        operation = (
            OperationKind.OPEN_MARKET_STREAM
            if session.stream_kind == "market"
            else OperationKind.OPEN_ORDER_STREAM
        )
        routing_request = RoutingRequest(
            operation=operation,
            trace_id=trace_id,
        )
        try:
            decision = self._router.route(routing_request)
        except Exception:
            logger.warning(
                "stream.failover.routing_failed",
                extra={"session_id": session_id, "current_broker": current_broker},
            )
            return False

        for fallback_broker in decision.fallback_brokers:
            if fallback_broker == current_broker:
                continue
            try:
                await self._disconnect_handle(session_id)
                gw = self._registry.get_gateway(fallback_broker)
                frame_cb = self._frame_handlers.get(session_id)
                plan = BrokerStreamPlan(
                    instruments=session.instruments,
                    modes=session.modes,
                    on_raw_frame=frame_cb,
                )
                if session.stream_kind == "market":
                    handle = await gw.open_market_stream(plan)
                else:
                    handle = await gw.open_order_stream(plan)

                async with self._lock:
                    self._handles[session_id] = handle
                session.update_transport(TransportState.CONNECTED)
                session.update_subscription(SubscriptionState.ACKNOWLEDGED)
                session.update_freshness(FreshnessState.UNKNOWN)
                session.reconnect_generation = 0

                object.__setattr__(session, "broker_id", fallback_broker)

                self._log_state_change(
                    session_id,
                    TransportState.RECONNECTING.value,
                    TransportState.CONNECTED.value,
                    f"failover:{current_broker}->{fallback_broker}",
                )
                logger.info(
                    "stream.failover.success",
                    extra={
                        "session_id": session_id,
                        "from_broker": current_broker,
                        "to_broker": fallback_broker,
                    },
                )
                return True
            except Exception as exc:
                logger.warning(
                    "stream.failover.broker_failed",
                    extra={
                        "session_id": session_id,
                        "fallback_broker": fallback_broker,
                        "error": str(exc),
                    },
                )
                continue

        logger.warning(
            "stream.failover.exhausted",
            extra={"session_id": session_id, "current_broker": current_broker},
        )
        return False

    # ------------------------------------------------------------------
    # Heartbeat / staleness
    # ------------------------------------------------------------------

    async def heartbeat_loop(self) -> None:
        """Periodic heartbeat: detect stale sessions and trigger failover."""
        while self._running():
            await asyncio.sleep(self._HEARTBEAT_INTERVAL_S)
            now = get_current_clock().now()
            for session_id, session in list(self._sessions.items()):
                self._check_freshness(session_id, session, now)

    def _check_freshness(self, session_id: str, session, now) -> None:
        """Update freshness state based on last valid tick time."""
        last = session.health.last_valid_tick_at
        if last is None:
            return

        elapsed = (now - last).total_seconds()
        if (
            elapsed > session.health.stale_seconds_threshold
            and session.health.freshness != FreshnessState.STALE
        ):
            session.update_freshness(FreshnessState.STALE)
            self._log_state_change(
                session_id,
                FreshnessState.FRESH.value,
                FreshnessState.STALE.value,
                f"no_valid_data_for_{elapsed:.0f}s",
            )
            self._tasks.append(
                asyncio.create_task(self._notify_health_change(session_id, session.health))
            )
