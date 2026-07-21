"""Canonical contracts for money-moving execution state.

These types are deliberately broker-agnostic.  Transport failures must remain
distinguishable from broker rejection so callers cannot safely retry an
ambiguous write without reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from domain.enums import OrderType, ProductType
from domain.enums import Side

if TYPE_CHECKING:
    from domain.ports.time_service import ClockPort


class SubmissionState(str, Enum):
    """Outcome of an order submission attempt."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """Durable order command persisted before broker I/O (ledger outbox).

    Prefer the alias :data:`PersistedOrderIntent` in new code (TOS-P1-002).
    Distinct from pre-risk :class:`domain.orders.intent.OrderIntent`.
    """

    intent_id: str
    order_id: str
    correlation_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal
    order_type: OrderType
    product_type: ProductType
    created_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.intent_id or not self.order_id or not self.correlation_id:
            raise ValueError("execution intent identifiers are required")
        if self.quantity <= 0:
            raise ValueError("execution intent quantity must be positive")
        if self.created_at.tzinfo is None:
            raise ValueError("execution intent timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SubmissionOutcome:
    """Durable broker result, including an unresolved transport outcome."""

    intent_id: str
    state: SubmissionState
    broker_order_id: str = ""
    reason: str = ""
    observed_at: datetime | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.intent_id:
            raise ValueError("submission outcome intent_id is required")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ValueError("submission outcome timestamp must be timezone-aware")
        if self.state is SubmissionState.ACCEPTED and not self.broker_order_id:
            raise ValueError("accepted submission requires broker_order_id")

    @classmethod
    def accepted(
        cls, intent_id: str, broker_order_id: str, clock: ClockPort | None = None
    ) -> SubmissionOutcome:
        from domain.ports.time_service import get_current_clock

        return cls(
            intent_id=intent_id,
            state=SubmissionState.ACCEPTED,
            broker_order_id=broker_order_id,
            observed_at=(clock or get_current_clock()).now(),
        )

    @classmethod
    def rejected(
        cls, intent_id: str, reason: str, clock: ClockPort | None = None
    ) -> SubmissionOutcome:
        from domain.ports.time_service import get_current_clock

        return cls(
            intent_id=intent_id,
            state=SubmissionState.REJECTED,
            reason=reason,
            observed_at=(clock or get_current_clock()).now(),
        )

    @classmethod
    def unknown(
        cls, intent_id: str, reason: str, clock: ClockPort | None = None
    ) -> SubmissionOutcome:
        from domain.ports.time_service import get_current_clock

        return cls(
            intent_id=intent_id,
            state=SubmissionState.UNKNOWN,
            reason=reason,
            observed_at=(clock or get_current_clock()).now(),
        )


@dataclass(frozen=True, slots=True)
class LedgerFillRecord:
    """Durable economic fill for ledger-backed recovery."""

    fill_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    cumulative_quantity: int
    order_quantity: int
    price: Decimal
    event_time: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.fill_id or not self.order_id:
            raise ValueError("ledger fill identifiers are required")
        if self.quantity <= 0:
            raise ValueError("ledger fill quantity must be positive")
        if self.event_time.tzinfo is None:
            raise ValueError("ledger fill event_time must be timezone-aware")


# Preferred name for durable ledger command (TOS-P1-002)
PersistedOrderIntent = OrderIntent
