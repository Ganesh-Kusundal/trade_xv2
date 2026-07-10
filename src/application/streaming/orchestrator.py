"""StreamOrchestrator — centralized WebSocket lifecycle management.

This component owns the full lifecycle of every broker stream session,
delegating to four specialised collaborators:

    broker_selector   — broker selection for new subscriptions
    session_manager   — connection lifecycle (open, disconnect, reuse)
    tick_router       — message normalization, dedup, fan-out to consumers
    reconnect_ctrl    — reconnect loop, cross-broker failover, heartbeat staleness

Architecture invariants
-----------------------
- Transport health, subscription integrity, and data freshness are modelled
  as orthogonal dimensions on ``StreamSession``.
- "Connected" is not "healthy" — a session must be connected + subscribed +
  receiving valid data within the SLA window.
- Reconnect is idempotent: the SubscriptionPlan is the source of truth, not
  consumer state.
- Slow consumers cannot block the broker read loop.
- Every state transition produces a structured ``stream.session.state_change``
  log event.

Consumer contract
-----------------
Consumers implement ``StreamConsumer`` and register via ``subscribe()``.
The orchestrator delivers normalized ``MarketTick`` and ``OrderResult`` objects.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from domain.candles.historical import InstrumentRef
from domain.ports.broker_gateway import BrokerStreamHandle
from domain.stream_health import (
    FreshnessState,
    StreamHealth,
    StreamSession,
    StreamStateSummary,
    SubscriptionState,
)
from infrastructure.time.clock import time_service

from application.streaming.broker_selector import BrokerSelector
from application.streaming.session_manager import SessionManager
from application.streaming.tick_router import TickRouter
from application.streaming.reconnect_controller import ReconnectController
from application.streaming.tick_router import _parse_exchange_time  # re-export for backward compat

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Consumer protocol
# ---------------------------------------------------------------------------


class StreamConsumer(Protocol):
    """Contract for downstream consumers of stream events."""

    def consumer_id(self) -> str: ...

    async def on_market_tick(self, tick: MarketTick) -> None: ...

    async def on_order_update(self, update: OrderUpdate) -> None: ...

    async def on_stream_health_change(self, session_id: str, health: StreamHealth) -> None: ...


# ---------------------------------------------------------------------------
# Normalized stream event types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketTick:
    """Normalized market data tick delivered to consumers."""

    instrument: InstrumentRef
    ltp: float
    volume: int
    bid: float | None
    ask: float | None
    broker_id: str
    session_id: str
    event_time: datetime
    sequence: int | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None


@dataclass(frozen=True)
class OrderUpdate:
    """Normalized order/position update delivered to consumers."""

    broker_id: str
    session_id: str
    event_time: datetime
    order_id: str = ""
    status: str = ""
    filled_qty: int = 0
    avg_price: float = 0.0
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Subscription plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionRequest:
    """Top-level subscription request into the orchestrator.

    stream_kind       — ``"market"``, ``"order"``, or ``"portfolio"``.
    instruments       — set of instruments (symbol:exchange strings) for market streams.
    modes             — broker-specific mode names, e.g. ``{"LTP", "FULL"}``.
    consumer          — the downstream consumer that will receive events.
    preferred_brokers — optional ordered list of broker_ids to use; auto-selects if empty.
    freshness_sla_s   — staleness threshold in seconds.
    allow_failover    — whether to failover to a fallback broker on staleness.
    """

    stream_kind: Literal["market", "order", "portfolio"]
    consumer: StreamConsumer
    instruments: frozenset[str] = field(default_factory=frozenset)
    modes: frozenset[str] = field(default_factory=frozenset)
    preferred_brokers: tuple[str, ...] = field(default_factory=tuple)
    freshness_sla_s: float = 30.0
    allow_failover: bool = True


@dataclass
class _ActiveSubscription:
    """Internal record tracking one consumer's subscription."""

    sub_id: str
    session_id: str
    consumer: StreamConsumer
    request: SubscriptionRequest
    registered_at: datetime = field(default_factory=lambda: time_service.now())


# ---------------------------------------------------------------------------
# StreamOrchestrator
# ---------------------------------------------------------------------------


class StreamOrchestrator:
    """Centralized stream lifecycle manager.

    Usage::

        orchestrator = StreamOrchestrator(registry=registry, router=router)
        await orchestrator.start()

        sub_id = await orchestrator.subscribe(SubscriptionRequest(...))
        # ... receive events via StreamConsumer callbacks ...
        await orchestrator.unsubscribe(sub_id)
        await orchestrator.stop()
    """

    def __init__(
        self,
        registry,
        router,
        *,
        max_consumer_queue: int = 1000,
        candle_aggregator=None,
    ) -> None:
        self._registry = registry
        self._router = router
        self._max_consumer_queue = max_consumer_queue

        # Shared mutable state
        self._sessions: dict[str, StreamSession] = {}
        self._handles: dict[str, BrokerStreamHandle] = {}
        self._subscriptions: dict[str, _ActiveSubscription] = {}
        self._session_frame_handlers: dict[str, Any] = {}
        self._session_reconnect_tasks: dict[str, asyncio.Task] = {}

        self._lock = asyncio.Lock()
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Optional live tick→candle aggregator
        self._candle_aggregator = candle_aggregator

        # Build collaborators (has-a composition)
        self._broker_selector = BrokerSelector(registry, router)

        self._tick_router = TickRouter(
            subscriptions=self._subscriptions,
            sessions=self._sessions,
            lock=self._lock,
            candle_aggregator=self._candle_aggregator,
        )

        self._session_manager = SessionManager(
            registry=registry,
            sessions=self._sessions,
            handles=self._handles,
            frame_handlers=self._session_frame_handlers,
            reconnect_tasks=self._session_reconnect_tasks,
            tasks=self._tasks,
            lock=self._lock,
            make_frame_callback=self._make_frame_callback,
            log_state_change=self._log_state_change,
        )

        self._reconnect = ReconnectController(
            registry=registry,
            router=router,
            sessions=self._sessions,
            handles=self._handles,
            frame_handlers=self._session_frame_handlers,
            lock=self._lock,
            running=lambda: self._running,
            tasks=self._tasks,
            log_state_change=self._log_state_change,
            notify_health_change=self._tick_router.notify_health_change,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start background monitoring tasks."""
        self._running = True
        self._tasks.append(
            asyncio.create_task(self._reconnect.heartbeat_loop(), name="stream.heartbeat")
        )
        logger.info("stream_orchestrator.started")

    async def stop(self) -> None:
        """Gracefully disconnect all sessions and stop monitoring."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        async with self._lock:
            session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self._session_manager.disconnect_session(sid, reason="orchestrator_stop")
        logger.info("stream_orchestrator.stopped")

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------

    async def subscribe(self, request: SubscriptionRequest) -> str:
        """Open or reuse a stream session and register the consumer.

        Returns a subscription ID that the caller uses to unsubscribe.
        """
        trace_id = str(uuid.uuid4())
        broker_id = await self._broker_selector.select_broker(request, trace_id)

        async with self._lock:
            existing = self._session_manager.find_reusable_session(broker_id, request)
            if existing is not None:
                session_id = existing.session_id
                await self._session_manager.merge_instruments(existing, request)
            else:
                session_id = await self._session_manager.open_session(
                    broker_id, request, trace_id,
                    reconnect_coro=self._reconnect.reconnect_loop,
                )

            sub_id = str(uuid.uuid4())
            self._subscriptions[sub_id] = _ActiveSubscription(
                sub_id=sub_id,
                session_id=session_id,
                consumer=request.consumer,
                request=request,
            )
            logger.info(
                "stream.subscribed",
                extra={
                    "sub_id": sub_id,
                    "session_id": session_id,
                    "broker_id": broker_id,
                    "stream_kind": request.stream_kind,
                    "consumer_id": request.consumer.consumer_id(),
                },
            )
            return sub_id

    async def unsubscribe(self, sub_id: str) -> None:
        """Remove a consumer subscription."""
        async with self._lock:
            sub = self._subscriptions.pop(sub_id, None)
            if sub is None:
                return
            remaining = [s for s in self._subscriptions.values() if s.session_id == sub.session_id]
            if not remaining:
                await self._session_manager.disconnect_session(
                    sub.session_id, reason="no_consumers"
                )

    # ------------------------------------------------------------------
    # Health queries
    # ------------------------------------------------------------------

    def session_health(self, session_id: str) -> StreamHealth | None:
        """Return the current health state of a session, or None if not found."""
        session = self._sessions.get(session_id)
        return session.health if session else None

    def all_sessions(self) -> list[StreamSession]:
        """Return a snapshot of all current sessions."""
        return list(self._sessions.values())

    def build_stream_summary(self, broker_id: str) -> StreamStateSummary:
        """Build a stream state summary for the given broker (for BrokerRegistry)."""
        sessions = [s for s in self._sessions.values() if s.broker_id == broker_id]
        healthy = sum(1 for s in sessions if s.is_healthy())
        stale = sum(1 for s in sessions if s.health.freshness == FreshnessState.STALE)
        degraded = sum(1 for s in sessions if s.health.subscription == SubscriptionState.DEGRADED)
        return StreamStateSummary(
            broker_id=broker_id,
            active_sessions=len(sessions),
            healthy_sessions=healthy,
            stale_sessions=stale,
            degraded_sessions=degraded,
        )

    # ------------------------------------------------------------------
    # Live candle aggregation (optional, OFF by default)
    # ------------------------------------------------------------------

    def attach_candle_aggregator(self, aggregator) -> None:
        """Attach a live tick→candle aggregator as an optional consumer.

        Once attached, every normalized market tick is fed to the aggregator
        in addition to registered consumers. Safe to call at runtime; pass
        ``None`` to detach.
        """
        self._candle_aggregator = aggregator
        self._tick_router._candle_aggregator = aggregator

    # ------------------------------------------------------------------
    # Internal wiring
    # ------------------------------------------------------------------

    def _make_frame_callback(self, session_id: str, stream_kind: str):
        """Build an on_raw_frame handler that bridges sync broker to asyncio."""

        def on_raw_frame(frame: Any) -> None:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                asyncio.ensure_future,
                self._tick_router.handle_frame(session_id, frame, stream_kind),
            )

        return on_raw_frame

    def _log_state_change(
        self,
        session_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> None:
        """Log and emit a structured state-change audit event."""
        session = self._sessions.get(session_id)
        broker_id = session.broker_id if session else "unknown"
        stream_kind = session.stream_kind if session else "market"
        reconnect_gen = session.reconnect_generation if session else 0
        logger.info(
            "stream.session.state_change",
            extra={
                "event": "stream.session.state_change",
                "session_id": session_id,
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "timestamp": time_service.now().isoformat(),
            },
        )
        with contextlib.suppress(Exception):
            from infrastructure.observability.audit import emit_stream_state_change

            emit_stream_state_change(
                session_id=session_id,
                broker_id=broker_id,
                stream_kind=stream_kind,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                reconnect_generation=reconnect_gen,
            )
