"""Core domain models — broker-agnostic trading objects."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from brokers.common.core.enums import (
    ExchangeSegment,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)


class OrderRequest(BaseModel):
    """Input model for placing an order."""

    security_id: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    correlation_id: str | None = None
    tag: str | None = None
    slice: bool = False
    market_protection: int = -1
    algo_name: str | None = None

    def estimated_value(self) -> Decimal | None:
        if self.price > 0 and self.quantity > 0:
            return self.price * Decimal(str(self.quantity))
        return None


class ModifyOrderRequest(BaseModel):
    """Input model for modifying an existing order."""

    order_id: str
    quantity: int | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: OrderType | None = None
    validity: Validity | None = None
    product_type: ProductType | None = None

    def to_changes(self) -> dict[str, object]:
        changes: dict[str, object] = {}
        for key, value in (
            ("quantity", self.quantity),
            ("price", self.price),
            ("trigger_price", self.trigger_price),
            ("order_type", self.order_type),
            ("validity", self.validity),
            ("product_type", self.product_type),
        ):
            if value is not None:
                changes[key] = value
        return changes


class OrderPreview(BaseModel):
    """Outcome of pre-flight order validation."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    notional: Decimal | None = None
    margin_required: Decimal | None = None


class SliceOrderRequest(BaseModel):
    """Request model for splitting a large order into child orders."""

    symbol: str
    exchange: str
    exchange_segment: ExchangeSegment
    transaction_type: TransactionType
    quantity: int
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    slice_quantity: int | None = None
    slice_count: int | None = None
    correlation_id: str | None = None


class PnlExitPolicy(BaseModel):
    """Policy for enabling Dhan PnL-exit automation."""

    profit_threshold: Decimal = Decimal("0")
    loss_threshold: Decimal = Decimal("0")
    enable_kill_switch: bool = True


class PnlExitResult(BaseModel):
    """Result returned by Dhan PnL-exit automation."""

    enabled: bool
    status: str = ""
    message: str = ""


class ConditionalAlert(BaseModel):
    """Conditional alert/order state."""

    alert_id: str = ""
    status: str = ""
    message: str = ""


class ConditionalAlertRequest(BaseModel):
    """Request model for placing a conditional alert."""

    symbol: str
    exchange: str
    exchange_segment: ExchangeSegment
    transaction_type: TransactionType
    quantity: int
    price: Decimal = Decimal("0")
    trigger_price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    comparison_type: str = "LTP"
    operator: str | None = None
    time_frame: str | None = None
    comparing_value: Decimal | None = None
    indicator_name: str | None = None
    comparing_indicator_name: str | None = None
    frequency: str | None = None
    expiry_date: str | None = None
    user_note: str | None = None


class Order(BaseModel):
    """Full broker-agnostic order."""

    order_id: str = ""
    correlation_id: str | None = None
    symbol: str = ""
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    remaining_quantity: int = 0
    average_price: Decimal = Decimal("0")
    order_timestamp: datetime | None = None
    exchange_order_id: str | None = None
    reject_reason: str | None = None
    total_value: Decimal = Decimal("0")
    instrument_type: InstrumentType = InstrumentType.EQUITY


class Position(BaseModel):
    """Current position for an instrument."""

    symbol: str = ""
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    quantity: int = 0
    buy_quantity: int = 0
    sell_quantity: int = 0
    buy_average_price: Decimal = Decimal("0")
    sell_average_price: Decimal = Decimal("0")
    net_quantity: int = 0
    net_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    instrument_type: InstrumentType = InstrumentType.EQUITY
    last_price: Decimal = Decimal("0")
    m2m_pnl: Decimal = Decimal("0")

    def pnl(self) -> Decimal:
        if self.net_quantity > 0:
            return Decimal(str(self.net_quantity)) * (self.last_price - self.buy_average_price)
        elif self.net_quantity < 0:
            return Decimal(str(abs(self.net_quantity))) * (
                self.sell_average_price - self.last_price
            )
        return Decimal("0")


class Holding(BaseModel):
    """Holding in the demat account."""

    symbol: str = ""
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    quantity: int = 0
    available_quantity: int = 0
    cost_price: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")
    pnl_value: Decimal = Decimal("0")
    instrument_type: InstrumentType = InstrumentType.EQUITY

    def pnl(self) -> Decimal:
        return Decimal(str(self.quantity)) * (self.last_price - self.cost_price)


class Trade(BaseModel):
    """An executed trade."""

    trade_id: str = ""
    order_id: str = ""
    exchange_order_id: str | None = None
    symbol: str = ""
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    transaction_type: TransactionType = TransactionType.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trade_value: Decimal = Decimal("0")
    trade_timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY

    def value(self) -> Decimal:
        if self.trade_value > 0:
            return self.trade_value
        return self.price * Decimal(str(self.quantity))


class FundLimits(BaseModel):
    """Account fund limits and margin details."""

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
    collateral: Decimal = Decimal("0")
    m2m_realized: Decimal = Decimal("0")
    m2m_unrealized: Decimal = Decimal("0")

    def has_sufficient(self, required: Decimal) -> bool:
        return self.available_balance >= required


class OrderResponse(BaseModel):
    """Response from order placement/modification/cancellation."""

    success: bool = False
    order_id: str | None = None
    exchange_order_id: str | None = None
    message: str = ""
    order_status: OrderStatus | None = None

    @classmethod
    def create_success(cls, order_id: str, message: str = "Success") -> OrderResponse:
        return cls(success=True, order_id=order_id, message=message)

    @classmethod
    def create_failure(cls, message: str) -> OrderResponse:
        return cls(success=False, message=message)


class Quote(BaseModel):
    """Market quote for an instrument."""

    symbol: str = ""
    security_id: str | None = None
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    last_price: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_quantity: int | None = None
    ask_quantity: int | None = None
    change: Decimal = Decimal("0")
    change_percent: Decimal = Decimal("0")
    timestamp: datetime | None = None

    def change_pct(self) -> Decimal:
        if self.close and self.close > 0:
            return ((self.last_price - self.close) / self.close) * Decimal("100")
        return Decimal("0")


class MarketDepthLevel(BaseModel):
    """Single bid/ask level in an order book."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


class MarketDepth(BaseModel):
    """Market-depth/order-book snapshot."""

    symbol: str = ""
    exchange: str = "NSE"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    bids: list[MarketDepthLevel] = []
    asks: list[MarketDepthLevel] = []
    timestamp: datetime | None = None

    @property
    def best_bid(self) -> MarketDepthLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> MarketDepthLevel | None:
        return self.asks[0] if self.asks else None


class HistoricalCandle(BaseModel):
    """OHLCV candle for historical data."""

    timestamp: datetime = Field(default_factory=datetime.now)
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0

    def body(self) -> Decimal:
        return self.close - self.open

    def range(self) -> Decimal:
        return self.high - self.low


class OptionContract(BaseModel):
    """Option chain contract with Greeks and market data."""

    symbol: str = ""
    strike: Decimal = Decimal("0")
    expiry: str = ""
    instrument_type: InstrumentType = InstrumentType.OPTIONS
    exchange: str = "NFO"
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE_FNO
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


class MarketDepthLevel5(BaseModel):
    """D5 (regular) depth level — Upstox V3 full mode."""

    bid_price: Decimal = Decimal("0")
    bid_qty: int = 0
    bid_orders: int = 0
    ask_price: Decimal = Decimal("0")
    ask_qty: int = 0
    ask_orders: int = 0


class MarketDepthLevel30(BaseModel):
    """D30 (Plus-only) depth level — Upstox V3 full_d30 mode."""

    bid_price: Decimal = Decimal("0")
    bid_qty: int = 0
    ask_price: Decimal = Decimal("0")
    ask_qty: int = 0


class MarketDepthD5(BaseModel):
    """Snapshot of 5-level market depth."""

    symbol: str = ""
    exchange: str = "NSE"
    timestamp: int = 0
    bids: list[MarketDepthLevel5] = []
    asks: list[MarketDepthLevel5] = []
    is_snapshot: bool = False


class MarketDepthD30(BaseModel):
    """Snapshot of 30-level market depth (Plus-only)."""

    symbol: str = ""
    exchange: str = "NSE"
    timestamp: int = 0
    bids: list[MarketDepthLevel30] = []
    asks: list[MarketDepthLevel30] = []
    is_snapshot: bool = False


class OrderBookSnapshot(BaseModel):
    """Full order-book snapshot (first 2 ticks of WS connection or REST)."""

    symbol: str = ""
    exchange: str = "NSE"
    depth: int = 5
    bids: list[MarketDepthLevel5] = []
    asks: list[MarketDepthLevel5] = []
    timestamp: int = 0


class OrderBookDelta(BaseModel):
    """Incremental update to the order book."""

    symbol: str = ""
    exchange: str = "NSE"
    changed_levels: list[dict[str, Any]] = []
    timestamp: int = 0


class OptionGreeksTick(BaseModel):
    """Tick carrying option Greeks (option_greeks WebSocket mode)."""

    instrument_key: str = ""
    timestamp: int = 0
    ltp: Decimal = Decimal("0")
    ltt: int = 0
    ltq: int = 0
    cp: Decimal = Decimal("0")
    first_bid_price: Decimal = Decimal("0")
    first_bid_qty: int = 0
    first_ask_price: Decimal = Decimal("0")
    first_ask_qty: int = 0
    greeks: dict[str, Decimal] = {}
    oi: int = 0
    iv: Decimal = Decimal("0")
    vtt: int = 0


class MarketStatusEvent(BaseModel):
    """First tick of every WebSocket connection — segment status."""

    timestamp_ms: int = 0
    segment_status: dict[str, str] = {}


class OrderUpdateEvent(BaseModel):
    """Portfolio stream event: order update."""

    order_id: str = ""
    status: str = ""
    filled_quantity: int = 0
    average_price: Decimal = Decimal("0")
    timestamp_ms: int = 0


class PositionUpdateEvent(BaseModel):
    """Portfolio stream event: position update."""

    instrument_key: str = ""
    quantity: int = 0
    day_buy_value: Decimal = Decimal("0")
    day_sell_value: Decimal = Decimal("0")
    sell_price: Decimal = Decimal("0")
    buy_price: Decimal = Decimal("0")
    product: str = ""
    exchange: str = ""
    timestamp_ms: int = 0


class HoldingUpdateEvent(BaseModel):
    """Portfolio stream event: holding update."""

    instrument_key: str = ""
    quantity: int = 0
    average_price: Decimal = Decimal("0")
    isin: str = ""
    product: str = ""
    exchange: str = ""
    timestamp_ms: int = 0


class GTTUpdateEvent(BaseModel):
    """Portfolio stream event: GTT update."""

    gtt_order_id: str = ""
    type: str = ""
    rules: list[dict[str, Any]] = []
    timestamp_ms: int = 0


class MarketIntelligenceSnapshot(BaseModel):
    """One-shot aggregate of market intelligence for an underlying."""

    underlying: str = ""
    as_of: datetime = Field(default_factory=datetime.now)
    pcr: Decimal | None = None
    max_pain: Decimal | None = None
    max_pain_insights: list[dict[str, Any]] = []
    total_call_oi: int | None = None
    total_put_oi: int | None = None
    spot_closing_price: Decimal | None = None
    oi_by_strike: list[dict[str, Any]] = []
    fii_flow: dict[str, Any] | None = None
    dii_flow: dict[str, Any] | None = None
    smartlist_futures: list[dict[str, Any]] = []
    smartlist_options: list[dict[str, Any]] = []
