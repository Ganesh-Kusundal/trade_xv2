"""Canonical domain dataclasses — value objects returned by broker adapters.

These are the single source of truth for every domain model that flows
through the system after the adapter boundary. DataFrames are used for
market data (OHLCV, quotes, option chain, depth); these dataclasses are
used for orders, positions, holdings, and trades.

Usage::

    from brokers.common.core.models import Order, Position

    order = Order(
        order_id="O-123",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2500"),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from brokers.common.core.types import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


@dataclass(slots=True, frozen=True)
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
    def average_price(self) -> Decimal:
        """Alias for avg_price — Dhan and some brokers use this name."""
        return self.avg_price

    @property
    def remaining_quantity(self) -> int:
        return max(self.quantity - self.filled_quantity, 0)

    @property
    def is_complete(self) -> bool:
        return self.status.is_terminal

    def with_status(self, status: OrderStatus) -> Order:
        """Return a new Order with the given status."""
        return replace(self, status=status)

    def with_fill(self, filled_quantity: int, avg_price: Decimal) -> Order:
        """Return a new Order with updated fill quantity and average fill price."""
        return replace(self, filled_quantity=filled_quantity, avg_price=avg_price)

    @classmethod
    def from_broker_dict(
        cls,
        d: dict,
        exchange_resolver: "Callable[[str], Any] | None" = None,
    ) -> "Order":
        """Construct a canonical Order from a broker-specific dict."""
        order_id = str(d.get("orderId", d.get("order_id", "")))
        symbol = str(d.get("tradingSymbol", d.get("symbol", "")))
        raw_exchange = d.get("exchangeSegment", d.get("exchange", "NSE"))
        exchange = exchange_resolver(raw_exchange) if exchange_resolver else raw_exchange
        side_str = str(d.get("transactionType", d.get("side", "BUY"))).upper()
        side = Side.BUY if side_str == "BUY" else Side.SELL

        ot_str = str(d.get("orderType", d.get("order_type", "MARKET"))).upper()
        _OT_ALIAS = {
            "STOPLOSS_LIMIT": "STOP_LOSS",
            "STOPLOSS_MARKET": "STOP_LOSS_MARKET",
            "STOPLOSS-MARKET": "STOP_LOSS_MARKET",
            "SL": "STOP_LOSS",
            "SLM": "STOP_LOSS_MARKET",
        }
        ot_str = _OT_ALIAS.get(ot_str, ot_str)
        try:
            order_type = OrderType(ot_str)
        except ValueError:
            order_type = OrderType.MARKET

        status_str = str(d.get("orderStatus", d.get("status", "OPEN"))).upper()
        status = OrderStatus.normalize(status_str)

        def _opt_dec(v: Any) -> Decimal | None:
            if v in (None, ""):
                return None
            return Decimal(str(v))

        return cls(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=order_type,
            quantity=int(d.get("quantity", 0)),
            filled_quantity=int(d.get("filledQty", d.get("filled_quantity", 0))),
            price=_opt_dec(d.get("price")) or Decimal("0"),
            avg_price=_opt_dec(d.get("averagePrice", d.get("avg_price", d.get("average_price")))) or Decimal("0"),
            status=status,
            reject_reason=str(d.get("rejectReason", d.get("reject_reason", ""))),
        )


@dataclass(slots=True, frozen=True)
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

    def with_ltp(self, ltp: Decimal) -> Position:
        """Return a new Position with the last traded price updated."""
        unrealized = (
            Decimal(str(self.quantity)) * (ltp - self.avg_price)
            if self.quantity != 0
            else Decimal("0")
        )
        return replace(self, ltp=ltp, unrealized_pnl=unrealized)

    def with_fill(self, quantity: int, price: Decimal) -> Position:
        """Return a new Position after applying a signed fill."""
        old_qty = self.quantity
        old_avg = self.avg_price
        delta = quantity
        new_qty = old_qty + delta

        if old_qty == 0:
            new_avg = price
            new_realized = self.realized_pnl
        elif (old_qty > 0 and delta < 0) or (old_qty < 0 and delta > 0):
            closed = min(abs(old_qty), abs(delta))
            pnl_factor = Decimal("1") if old_qty > 0 else Decimal("-1")
            new_realized = self.realized_pnl + Decimal(str(closed)) * (price - old_avg) * pnl_factor
            if new_qty == 0:
                new_avg = Decimal("0")
            elif abs(delta) > abs(old_qty):
                new_avg = price
            else:
                new_avg = old_avg
        else:
            new_realized = self.realized_pnl
            new_avg = (Decimal(str(old_qty)) * old_avg + Decimal(str(delta)) * price) / Decimal(str(new_qty))

        unrealized = (
            Decimal(str(new_qty)) * (price - new_avg)
            if new_qty != 0
            else Decimal("0")
        )
        return replace(
            self,
            quantity=new_qty,
            avg_price=new_avg,
            ltp=price,
            unrealized_pnl=unrealized,
            realized_pnl=new_realized,
        )


@dataclass(slots=True, frozen=True)
class Holding:
    """Canonical holding — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    available_quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")


@dataclass(slots=True, frozen=True)
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


@dataclass(slots=True, frozen=True)
class Balance:
    """Canonical account balance — returned by every broker adapter."""

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    utilized_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")


@dataclass(slots=True, frozen=True)
class DepthLevel:
    """Single price level in market depth."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


@dataclass(slots=True, frozen=False)
class MarketDepth:
    """Canonical market depth — bid/ask ladder."""

    symbol: str = ""
    bids: list[DepthLevel] | None = None
    asks: list[DepthLevel] | None = None
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.bids is None:
            self.bids = []
        if self.asks is None:
            self.asks = []


@dataclass(slots=True, frozen=True)
class Quote:
    """Canonical quote snapshot — returned by every broker adapter."""

    symbol: str
    ltp: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
    timestamp: datetime | None = None


@dataclass(slots=True, frozen=False)
class Instrument:
    """Canonical instrument master record — returned by broker adapters.

    This is the broker-adapter-level instrument, populated by Dhan/Upstox
    instrument loaders. Distinct from:

    * ``brokers.common.core.instruments.Instrument`` — the trading-engine
      instrument used by the strategy layer (has ``asset_class``,
      ``broker_identifier``).
    * ``brokers.dhan.domain.Instrument`` — Dhan-specific instrument with
      typed ``Exchange`` and ``InstrumentType`` enums.
    """

    symbol: str
    exchange: str
    security_id: str
    instrument_type: str
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    name: str | None = None
    option_type: str | None = None
    strike_price: Decimal | None = None
    expiry: str | None = None
    underlying: str | None = None
    canonical_symbol: str | None = None


@dataclass(slots=True, frozen=False)
class OptionContract:
    """Option chain contract with greeks and market data."""

    strike: Decimal = Decimal("0")
    expiry: str = ""
    instrument_type: str = "OPTION"
    exchange: str = "NFO"
    lot_size: int = 0
    ce_ltp: Decimal | None = None
    ce_bid: Decimal | None = None
    ce_ask: Decimal | None = None
    ce_iv: Decimal | None = None
    ce_oi: int | None = None
    ce_volume: int | None = None
    pe_ltp: Decimal | None = None
    pe_bid: Decimal | None = None
    pe_ask: Decimal | None = None
    pe_iv: Decimal | None = None
    pe_oi: int | None = None
    pe_volume: int | None = None


@dataclass(slots=True, frozen=False)
class ConditionalAlert:
    """Conditional alert state."""

    alert_id: str = ""
    symbol: str = ""
    condition: str = ""
    status: str = "ACTIVE"


@dataclass(slots=True, frozen=False)
class ConditionalAlertRequest:
    """Request model for placing a conditional alert."""

    symbol: str = ""
    exchange: str = "NSE"
    condition_type: str = ""
    threshold: Decimal = Decimal("0")


@dataclass(slots=True, frozen=False)
class MarketIntelligenceSnapshot:
    """One-shot aggregate of market intelligence for an underlying."""

    underlying: str = ""
    pcr: Decimal = Decimal("0")
    max_pain: Decimal = Decimal("0")
    oi_data: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=False)
class PnlExitPolicy:
    """Policy for PnL-based exit automation."""

    target_pnl: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")


@dataclass(slots=True, frozen=False)
class PnlExitResult:
    """Result returned by PnL-exit automation."""

    success: bool = False
    message: str = ""
