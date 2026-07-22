"""Domain events — immutable Message hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from domain.enums import OrderSide, RiskLevel
from domain.value_objects import (
    ComponentId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    timestamp: datetime
    correlation_id: UUID | None = None
    source: ComponentId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent(Message):
    """Base domain event."""


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderPlaced(DomainEvent):
    order_id: OrderId
    instrument_id: InstrumentId
    side: OrderSide
    quantity: Quantity


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderFilled(DomainEvent):
    order_id: OrderId
    instrument_id: InstrumentId
    side: OrderSide
    filled_qty: Quantity
    avg_price: Price


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderCancelled(DomainEvent):
    order_id: OrderId
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderRejected(DomainEvent):
    order_id: OrderId
    reason: str
    venue_code: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PositionChanged(DomainEvent):
    instrument_id: InstrumentId
    quantity: Quantity
    avg_price: Price
    realized_pnl: Money
    unrealized_pnl: Money


@dataclass(frozen=True, slots=True, kw_only=True)
class RiskBreached(DomainEvent):
    level: RiskLevel
    reason: str
    instrument_id: InstrumentId | None = None
