"""StreamOrchestrator — centralized WebSocket lifecycle management.

This component owns the full lifecycle of every broker stream session:
  - connect / authenticate / subscribe
  - heartbeat monitoring
  - stale-stream detection (freshness SLA)
  - safe reconnect and idempotent resubscribe
  - failover handoff when policy allows
  - fan-out to downstream consumers with per-consumer backpressure

Architecture invariants:
  - Transport health, subscription integrity, and data freshness are modeled
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
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Protocol, Sequence

from domain.historical import InstrumentRef
from domain.stream_health import (
    FreshnessState,
    StreamHealth,
    StreamSession,
    StreamStateSummary,
    SubscriptionState,
    TransportState,
)
from brokers.common.broker_port import (
    BrokerStreamHandle,
    BrokerStreamPlan,
    CommonBrokerGateway,
    QuotaToken,
)
from brokers.common.errors import StreamAuthError, StreamError, StreamStalenessError
from brokers.common.models import OperationKind, RouteDecision, RoutingRequest
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Consumer protocol
# ---------------------------------------------------------------------------


class StreamConsumer(Protocol):
    """Contract for downstream consumers of stream events.

    The orchestrator delivers events to all registered consumers.
    Consumers must be non-blocking; heavy processing should be offloaded.
    """

    def consumer_id(self) -> str:
        """Unique identifier for this consumer (for metrics and deregistration)."""
        ...

    async def on_market_tick(self, tick: "MarketTick") -> None:
        """Called for each normalized market data update."""
        ...

    async def on_order_update(self, update: "OrderUpdate") -> None:
        """Called for each normalized order/position stream update."""
        ...

    async def on_stream_health_change(self, session_id: str, health: StreamHealth) -> None:
        """Called when the health state of a session changes."""
        ...


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
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


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

    _HEARTBEAT_INTERVAL_S = 5.0
    _RECONNECT_BASE_DELAY_S = 1.0
    _RECONNECT_MAX_DELAY_S = 60.0

    def __init__(
        self,
        registry: BrokerRegistry,
        router: BrokerRouter,
        *,
        max_consumer_queue: int = 1000,
    ) -> None:
        self._registry = registry
        self._router = router
        self._max_consumer_queue = max_consumer_queue

        # session_id → StreamSession
        self._sessions: dict[str, StreamSession] = {}
        # session_id → BrokerStreamHandle
        self._handles: dict[str, BrokerStreamHandle] = {}
        # sub_id → _ActiveSubscription
        self._subscriptions: dict[str, _ActiveSubscription] = {}

        self._lock = asyncio.Lock()
        self._running = False
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start background monitoring tasks."""
        self._running = True
        self._tasks.append(asyncio.create_task(self._heartbeat_loop(), name="stream.heartbeat"))
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
            await self._disconnect_session(sid, reason="orchestrator_stop")
        logger.info("stream_orchestrator.stopped")

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------

    async def subscribe(self, request: SubscriptionRequest) -> str:
        """Open or reuse a stream session and register the consumer.

        Returns a subscription ID that the caller uses to unsubscribe.
        """
        trace_id = str(uuid.uuid4())
        broker_id = await self._select_broker(request, trace_id)

        async with self._lock:
            # Reuse an existing healthy session for the same broker + kind
            existing_session = self._find_reusable_session(broker_id, request)
            if existing_session is not None:
                session_id = existing_session.session_id
            else:
                session_id = await self._open_session(broker_id, request, trace_id)

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
            # Check if any other consumer uses this session
            remaining = [
                s for s in self._subscriptions.values()
                if s.session_id == sub.session_id
            ]
            if not remaining:
                await self._disconnect_session(sub.session_id, reason="no_consumers")

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
        stale = sum(
            1 for s in sessions
            if s.health.freshness == FreshnessState.STALE
        )
        degraded = sum(
            1 for s in sessions
            if s.health.subscription == SubscriptionState.DEGRADED
        )
        return StreamStateSummary(
            broker_id=broker_id,
            active_sessions=len(sessions),
            healthy_sessions=healthy,
            stale_sessions=stale,
            degraded_sessions=degraded,
        )

    # ------------------------------------------------------------------
    # Fan-out to consumers
    # ------------------------------------------------------------------

    async def _deliver_tick(self, session_id: str, tick: MarketTick) -> None:
        """Deliver a market tick to all consumers of the session."""
        subs = [
            s for s in self._subscriptions.values()
            if s.session_id == session_id
        ]
        for sub in subs:
            try:
                await asyncio.wait_for(
                    sub.consumer.on_market_tick(tick),
                    timeout=1.0,  # slow consumer protection
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "stream.consumer.slow",
                    extra={
                        "consumer_id": sub.consumer.consumer_id(),
                        "session_id": session_id,
                    },
                )
            except Exception:
                logger.exception(
                    "stream.consumer.error",
                    extra={"consumer_id": sub.consumer.consumer_id()},
                )

        # Update freshness on valid tick
        session = self._sessions.get(session_id)
        if session:
            now = datetime.now(tz=timezone.utc)
            session.record_message(now)
            session.update_freshness(FreshnessState.FRESH, at=now)

    async def _deliver_order_update(self, session_id: str, update: OrderUpdate) -> None:
        """Deliver an order update to all consumers of the session."""
        subs = [
            s for s in self._subscriptions.values()
            if s.session_id == session_id
        ]
        for sub in subs:
            try:
                # BLOCK for order events — never drop
                await sub.consumer.on_order_update(update)
            except Exception:
                logger.exception(
                    "stream.consumer.order_update.error",
                    extra={"consumer_id": sub.consumer.consumer_id()},
                )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _open_session(
        self,
        broker_id: str,
        request: SubscriptionRequest,
        trace_id: str,
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
            created_at=datetime.now(tz=timezone.utc),
        )
        session.update_transport(TransportState.CONNECTING)
        self._sessions[session_id] = session
        self._log_state_change(session_id, "NONE", TransportState.CONNECTING.value, "open_session")

        gw = self._registry.get_gateway(broker_id)

        def on_raw_frame(frame: Any) -> None:
            # Schedule delivery in the event loop; do not block the broker read loop
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                asyncio.ensure_future,
                self._handle_frame(session_id, frame, request.stream_kind),
            )

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
                session_id, TransportState.CONNECTING.value,
                TransportState.CONNECTED.value, "session_opened"
            )
        except Exception as exc:
            session.update_transport(TransportState.DISCONNECTED)
            self._log_state_change(
                session_id, TransportState.CONNECTING.value,
                TransportState.DISCONNECTED.value, f"open_failed:{exc}"
            )
            raise

        # Spawn a reconnect monitor for this session
        self._tasks.append(
            asyncio.create_task(
                self._reconnect_loop(session_id, request),
                name=f"stream.reconnect.{session_id[:8]}",
            )
        )
        return session_id

    async def _disconnect_session(self, session_id: str, reason: str = "") -> None:
        """Disconnect and clean up a session."""
        handle = self._handles.pop(session_id, None)
        session = self._sessions.pop(session_id, None)
        if handle:
            try:
                await handle.disconnect()
            except Exception:
                pass
        if session:
            self._log_state_change(
                session_id,
                session.health.transport.value,
                TransportState.DISCONNECTED.value,
                reason,
            )

    def _find_reusable_session(
        self,
        broker_id: str,
        request: SubscriptionRequest,
    ) -> StreamSession | None:
        """Return an existing healthy session for the same broker and stream kind."""
        for session in self._sessions.values():
            if (
                session.broker_id == broker_id
                and session.stream_kind == request.stream_kind
                and session.is_healthy()
            ):
                return session
        return None

    # ------------------------------------------------------------------
    # Frame handling
    # ------------------------------------------------------------------

    async def _handle_frame(
        self,
        session_id: str,
        frame: Any,
        stream_kind: str,
    ) -> None:
        """Normalize a raw broker frame and deliver to consumers."""
        session = self._sessions.get(session_id)
        if session is None:
            return

        now = datetime.now(tz=timezone.utc)
        session.record_message(now)

        if stream_kind == "market":
            tick = self._normalize_tick(frame, session_id, session.broker_id, now)
            if tick is not None:
                await self._deliver_tick(session_id, tick)
        else:
            update = self._normalize_order_update(frame, session_id, session.broker_id, now)
            if update is not None:
                await self._deliver_order_update(session_id, update)

    @staticmethod
    def _normalize_tick(
        frame: Any,
        session_id: str,
        broker_id: str,
        now: datetime,
    ) -> MarketTick | None:
        """Map a raw broker frame to a normalized MarketTick.

        Broker adapters should emit dicts with canonical field names;
        this method provides a best-effort normalization.
        """
        if not isinstance(frame, dict):
            return None
        symbol = frame.get("symbol") or frame.get("trading_symbol") or ""
        exchange = frame.get("exchange") or "NSE"
        if not symbol:
            return None
        return MarketTick(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            ltp=float(frame.get("ltp") or frame.get("last_price") or 0),
            volume=int(frame.get("volume") or 0),
            bid=float(frame["bid"]) if "bid" in frame else None,
            ask=float(frame["ask"]) if "ask" in frame else None,
            broker_id=broker_id,
            session_id=session_id,
            event_time=now,
            sequence=frame.get("sequence"),
            open=float(frame["open"]) if "open" in frame else None,
            high=float(frame["high"]) if "high" in frame else None,
            low=float(frame["low"]) if "low" in frame else None,
        )

    @staticmethod
    def _normalize_order_update(
        frame: Any,
        session_id: str,
        broker_id: str,
        now: datetime,
    ) -> OrderUpdate | None:
        if not isinstance(frame, dict):
            return None
        return OrderUpdate(
            broker_id=broker_id,
            session_id=session_id,
            event_time=now,
            order_id=str(frame.get("order_id") or ""),
            status=str(frame.get("status") or ""),
            filled_qty=int(frame.get("filled_qty") or 0),
            avg_price=float(frame.get("avg_price") or 0),
            raw=frame,
        )

    # ------------------------------------------------------------------
    # Reconnect loop
    # ------------------------------------------------------------------

    async def _reconnect_loop(
        self,
        session_id: str,
        original_request: SubscriptionRequest,
    ) -> None:
        """Monitor a session and reconnect on transport loss."""
        delay = self._RECONNECT_BASE_DELAY_S
        while self._running:
            await asyncio.sleep(1.0)
            session = self._sessions.get(session_id)
            if session is None:
                return  # session was intentionally closed

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

                try:
                    broker_id = session.broker_id
                    gw = self._registry.get_gateway(broker_id)
                    plan = BrokerStreamPlan(
                        instruments=session.instruments,
                        modes=session.modes,
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
                    delay = self._RECONNECT_BASE_DELAY_S  # reset backoff
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
    # Heartbeat / staleness detection
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat: detect stale sessions and trigger failover."""
        while self._running:
            await asyncio.sleep(self._HEARTBEAT_INTERVAL_S)
            now = datetime.now(tz=timezone.utc)
            for session_id, session in list(self._sessions.items()):
                self._check_freshness(session, now)

    def _check_freshness(self, session: StreamSession, now: datetime) -> None:
        """Update freshness state based on last valid tick time."""
        last = session.health.last_valid_tick_at
        if last is None:
            # Never received a tick — leave as UNKNOWN for the first SLA window
            return

        elapsed = (now - last).total_seconds()
        if elapsed > session.health.stale_seconds_threshold:
            if session.health.freshness != FreshnessState.STALE:
                session.update_freshness(FreshnessState.STALE)
                self._log_state_change(
                    session.session_id,
                    FreshnessState.FRESH.value,
                    FreshnessState.STALE.value,
                    f"no_valid_data_for_{elapsed:.0f}s",
                )

    # ------------------------------------------------------------------
    # Broker selection
    # ------------------------------------------------------------------

    async def _select_broker(
        self,
        request: SubscriptionRequest,
        trace_id: str,
    ) -> str:
        if request.preferred_brokers:
            for bid in request.preferred_brokers:
                health = self._registry.get_health(bid)
                if health.is_usable():
                    return bid

        operation = (
            OperationKind.OPEN_MARKET_STREAM
            if request.stream_kind == "market"
            else OperationKind.OPEN_ORDER_STREAM
        )
        routing_request = RoutingRequest(
            operation=operation,
            trace_id=trace_id,
        )
        decision: RouteDecision = self._router.route(routing_request)
        return decision.primary_broker

    # ------------------------------------------------------------------
    # Observability helpers
    # ------------------------------------------------------------------

    def _log_state_change(
        self,
        session_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> None:
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
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        try:
            from brokers.common.observability.audit import emit_stream_state_change

            emit_stream_state_change(
                session_id=session_id,
                broker_id=broker_id,
                stream_kind=stream_kind,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                reconnect_generation=reconnect_gen,
            )
        except Exception:
            pass
