"""Domain entities — Order FSM + market/portfolio snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal

from domain.enums import (
    AssetClass,
    ExchangeId,
    InstrumentType,
    OptionType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
    TimeFrame,
)

_LEGAL: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.SUBMITTED}),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.UNKNOWN: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Order:
    order_id: OrderId
    instrument_id: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: Quantity
    price: Price | None
    time_in_force: TimeInForce
    status: OrderStatus
    correlation_id: CorrelationId
    filled_quantity: Quantity = field(default_factory=lambda: Quantity(value=Decimal("0")))

    def transition_to(self, new_status: OrderStatus) -> Order:
        allowed = _LEGAL[self.status]
        if new_status not in allowed:
            raise ValueError(f"illegal transition {self.status.name} → {new_status.name}")
        return replace(self, status=new_status)


@dataclass(frozen=True, slots=True)
class Position:
    instrument_id: InstrumentId
    quantity: Quantity
    avg_price: Price
    realized_pnl: Money
    unrealized_pnl: Money


@dataclass(frozen=True, slots=True)
class Trade:
    trade_id: str
    order_id: OrderId
    instrument_id: InstrumentId
    price: Price
    quantity: Quantity
    side: OrderSide
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class Quote:
    instrument_id: InstrumentId
    bid: Price
    ask: Price
    bid_size: Quantity
    ask_size: Quantity
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class Bar:
    instrument_id: InstrumentId
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity
    timeframe: TimeFrame
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: Price
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class MarketDepth:
    instrument_id: InstrumentId
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: InstrumentId
    symbol: str
    exchange: ExchangeId
    asset_class: AssetClass
    currency: str
    instrument_type: InstrumentType
    underlying_id: InstrumentId | None = None
    strike: Decimal | None = None
    expiry: datetime | None = None
    option_type: OptionType | None = None


@dataclass
class Account:
    account_id: AccountId
    balance: Money
    margin: Money
    equity: Money
