"""Canonical domain models — strongly typed, broker-agnostic.

These replace the Pydantic models for domain objects that flow through
the system after the adapter boundary.  DataFrames are used for
market data (OHLCV, quotes, option chain, depth); domain objects are
used for orders, positions, holdings, and trades.

Usage::

    from brokers.common.core.domain import Order, Position, Side, OrderStatus

    order = Order(
        order_id="O-123",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        status=OrderStatus.FILLED,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

# ── Canonical Enums ────────────────────────────────────────────────────────


class Side(str, Enum):
    """Order side — BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Canonical order status.

    Broker-specific variants (TRANSIT, TRIGGER PENDING, COMPLETE, etc.)
    must be normalized to these values at the adapter boundary.
    """

    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @classmethod
    def normalize(cls, broker_status: str) -> OrderStatus:
        """Map broker-specific status strings to canonical status."""
        normalized = broker_status.upper().strip().replace(" ", "_")

        _MAP: dict[str, OrderStatus] = {
            # Direct matches
            "OPEN": cls.OPEN,
            "PARTIALLY_FILLED": cls.PARTIALLY_FILLED,
            "FILLED": cls.FILLED,
            "CANCELLED": cls.CANCELLED,
            "REJECTED": cls.REJECTED,
            "EXPIRED": cls.EXPIRED,
            # Common broker-specific → canonical
            "EXECUTED": cls.FILLED,
            "COMPLETE": cls.FILLED,
            "TRIGGER_PENDING": cls.OPEN,
            "TRANSIT": cls.OPEN,
            "PENDING": cls.OPEN,
            "PLACED": cls.OPEN,
            "TRIGGERED": cls.OPEN,
            "PARTIALLY_EXECUTED": cls.PARTIALLY_FILLED,
            "PARTIALLY_CANCELLED": cls.PARTIALLY_FILLED,
        }

        return _MAP.get(normalized, cls.OPEN)

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }


class ProductType(str, Enum):
    """Canonical product types."""

    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"


class OrderType(str, Enum):
    """Canonical order types."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class Validity(str, Enum):
    """Order validity."""

    DAY = "DAY"
    IOC = "IOC"


# ── Domain Models ──────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=False)
class Order:
    """Canonical order — returned by every broker adapter."""

    order_id: str
    symbol: str
    exchange: str
    side: Side
    order_type: OrderType
    quantity: int
    filled_quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.OPEN
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    avg_price: Decimal = Decimal("0")
    reject_reason: str = ""
    correlation_id: str | None = None

    @property
    def remaining_quantity(self) -> int:
        return max(self.quantity - self.filled_quantity, 0)

    @property
    def is_complete(self) -> bool:
        return self.status.is_terminal


@dataclass(slots=True, frozen=False)
class Position:
    """Canonical position — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY

    @property
    def pnl(self) -> Decimal:
        if self.quantity > 0:
            return Decimal(str(self.quantity)) * (self.ltp - self.avg_price)
        elif self.quantity < 0:
            return Decimal(str(abs(self.quantity))) * (self.avg_price - self.ltp)
        return Decimal("0")


@dataclass(slots=True, frozen=False)
class Holding:
    """Canonical holding — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    available_quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")


@dataclass(slots=True, frozen=False)
class Trade:
    """Canonical trade — returned by every broker adapter."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    trade_value: Decimal = Decimal("0")
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY

    @property
    def value(self) -> Decimal:
        if self.trade_value > 0:
            return self.trade_value
        return self.price * Decimal(str(self.quantity))


@dataclass(slots=True, frozen=False)
class FundLimits:
    """Canonical fund limits — returned by every broker adapter."""

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")

    def has_sufficient(self, required: Decimal) -> bool:
        return self.available_balance >= required


@dataclass(slots=True, frozen=False)
class OrderResponse:
    """Canonical response from order placement/modification/cancellation."""

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN

    @classmethod
    def ok(cls, order_id: str, message: str = "Success") -> OrderResponse:
        return cls(success=True, order_id=order_id, message=message)

    @classmethod
    def fail(cls, message: str) -> OrderResponse:
        return cls(success=False, message=message)
