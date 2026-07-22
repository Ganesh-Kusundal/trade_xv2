"""Canonical event-type catalogue for the in-process event bus.

Split into focused modules (ADR-010):
- ``types.py`` (this file): DomainEvent, EventType enum
- ``payloads.py``: EventPayload, EVENT_PAYLOADS, make_payload
- ``typed_events.py``: TypedDomainEvent, typed event wrappers
- ``trade_id.py``: TradeIdKey

All symbols remain importable from ``domain.events.types`` for backward
compatibility — the original imports continue to work unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from domain.parsing import require_tz_aware

EVENT_ID_HEX_LENGTH = 16


@dataclass(frozen=True)
class DomainEvent:
    """An immutable domain event — the core value object for the event bus.

    This is a pure domain concept. The event bus infrastructure
    (publish/subscribe/dispatch) lives in ``infrastructure.event_bus``;
    the event *shape* lives here in domain.
    """

    event_type: str
    timestamp: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)
    symbol: str | None = None
    source: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:EVENT_ID_HEX_LENGTH])
    correlation_id: str | None = None
    sequence_number: int = 0

    def __post_init__(self) -> None:
        require_tz_aware(
            self.timestamp,
            f"DomainEvent requires timezone-aware timestamps. "
            f"Got naive datetime: {self.timestamp}. "
            f"Use DomainEvent.now() factory or provide tzinfo explicitly.",
        )
        # Defensive copy: freeze a fresh dict, not a view over the caller's
        # mutable one, so mutating the caller's dict after construction
        # cannot leak into the event's payload.
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @classmethod
    def now(
        cls,
        event_type: str,
        payload: dict[str, Any] | None = None,
        symbol: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        sequence_number: int = 0,
    ) -> DomainEvent:
        """Create an event with the current timestamp.

        If *correlation_id* is not provided, the current thread's active
        correlation ID is used for automatic end-to-end tracing.
        """
        from domain.ports.time_service import get_current_clock

        if correlation_id is None:
            from domain.correlation import get_current_correlation_id

            correlation_id = get_current_correlation_id()
        return cls(
            event_type=event_type,
            timestamp=get_current_clock().now(),
            payload=payload or {},
            symbol=symbol,
            source=source,
            correlation_id=correlation_id,
            sequence_number=sequence_number,
        )


class EventType(str, Enum):
    """Canonical event types published on the :class:`EventBus`.

    Inheriting from :class:`str`` means existing ``==`` comparisons
    with bare strings continue to work.
    """

    # ── Market data ────────────────────────────────────────────────────
    TICK = "TICK"
    DEPTH = "DEPTH"
    QUOTE = "QUOTE"
    DEPTH_20 = "DEPTH_20"
    DEPTH_30 = "DEPTH_30"
    DEPTH_200 = "DEPTH_200"
    INDEX_QUOTE = "INDEX_QUOTE"
    OPTION_CHAIN = "OPTION_CHAIN"

    # ── Orders / OMS ───────────────────────────────────────────────────
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_UPDATED = "ORDER_UPDATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    TRADE = "TRADE"
    TRADE_FILLED = "TRADE_FILLED"
    TRADE_APPLIED = "TRADE_APPLIED"

    # ── Risk / position ────────────────────────────────────────────────
    RISK_LIMIT_BREACHED = "RISK_LIMIT_BREACHED"

    # ── Reconciliation ─────────────────────────────────────────────────
    RECONCILIATION_DRIFT = "RECONCILIATION_DRIFT"

    # ── Lifecycle / system ─────────────────────────────────────────────
    SERVICE_STARTED = "SERVICE_STARTED"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    SERVICE_FAILED = "SERVICE_FAILED"

    # ── Legacy (still published by existing callers) ──────────────────
    POSITION_UPDATED = "POSITION_UPDATED"
    BAR_CLOSED = "BAR_CLOSED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"

    # ── Additional Risk Events ───────────────────────────────────────
    KILL_SWITCH_TOGGLED = "KILL_SWITCH_TOGGLED"
    DAILY_PNL_RESET = "DAILY_PNL_RESET"
    DRAWDOWN_LIMIT_HIT = "DRAWDOWN_LIMIT_HIT"

    # ── Broker Connectivity Events ───────────────────────────────────
    BROKER_CONNECTED = "BROKER_CONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    CIRCUIT_BREAKER_OPENED = "CIRCUIT_BREAKER_OPENED"
    CIRCUIT_BREAKER_CLOSED = "CIRCUIT_BREAKER_CLOSED"

    # ── Scanner Events ───────────────────────────────────────────────
    SCAN_STARTED = "SCAN_STARTED"
    CANDIDATE_GENERATED = "CANDIDATE_GENERATED"
    SCAN_COMPLETED = "SCAN_COMPLETED"

    # ── Strategy Events ──────────────────────────────────────────────
    SIGNAL_EXECUTED = "SIGNAL_EXECUTED"

    # ── Markets Layer Events ─────────────────────────────────────────
    QUOTE_UPDATED = "QUOTE_UPDATED"
    DEPTH_UPDATED = "DEPTH_UPDATED"
    SUBSCRIPTION_STARTED = "SUBSCRIPTION_STARTED"
    SUBSCRIPTION_ENDED = "SUBSCRIPTION_ENDED"

    # ── Position Lifecycle Events ────────────────────────────────────
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"

    # ── Health / System Events ───────────────────────────────────────
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    HEALTH_CHECK_PASSED = "HEALTH_CHECK_PASSED"
    HEALTH_CHECK_FAILED = "HEALTH_CHECK_FAILED"

    # ── Risk Decision Events ────────────────────────────────────────
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"

    # ── Portfolio & Metrics Events ─────────────────────────────────
    PORTFOLIO_UPDATED = "PORTFOLIO_UPDATED"
    METRICS_UPDATED = "METRICS_UPDATED"

    # ── Scanner/Strategy Lifecycle Events ──────────────────────────
    SCANNER_STATE_CHANGED = "SCANNER_STATE_CHANGED"
    STRATEGY_ACTIVATED = "STRATEGY_ACTIVATED"
    STRATEGY_PAUSED = "STRATEGY_PAUSED"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"

    # ── Execution Planning Events ────────────────────────────────
    EXECUTION_PLAN_BUILT = "EXECUTION_PLAN_BUILT"
    ORDER_REQUESTED = "ORDER_REQUESTED"


# ── Backward-compatible re-exports ──────────────────────────────────────
# All symbols previously in this file remain importable from here.
from domain.events.payloads import (  # noqa: E402
    EVENT_PAYLOADS,
    EventPayload,
    canonical_event_types,
    make_payload,
)
from domain.events.trade_id import TradeIdKey  # noqa: E402
from domain.events.typed_events import (  # noqa: E402
    ExecutionPlanBuiltEvent,
    OrderFilledEvent,
    OrderRequestedEvent,
    OrderUpdatedEvent,
    PositionClosedEvent,
    QuoteUpdatedEvent,
    TradeAppliedEvent,
    TradeFilledEvent,
    TypedDomainEvent,
    to_typed_event,
)

__all__ = [
    # Re-exported from payloads.py
    "EVENT_PAYLOADS",
    # Core types (defined here)
    "DomainEvent",
    "EventPayload",
    "EventType",
    # Re-exported from typed_events.py
    "ExecutionPlanBuiltEvent",
    "OrderFilledEvent",
    "OrderRequestedEvent",
    "OrderUpdatedEvent",
    "PositionClosedEvent",
    "QuoteUpdatedEvent",
    "TradeAppliedEvent",
    "TradeFilledEvent",
    # Re-exported from trade_id.py
    "TradeIdKey",
    "TypedDomainEvent",
    "canonical_event_types",
    "make_payload",
    "to_typed_event",
]
