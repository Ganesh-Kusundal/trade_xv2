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

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
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
            "TRADED": cls.FILLED,
            "TRIGGER_PENDING": cls.OPEN,
            "TRANSIT": cls.OPEN,
            "PENDING": cls.OPEN,
            "PLACED": cls.OPEN,
            "TRIGGERED": cls.OPEN,
            "OPEN_PENDING": cls.OPEN,
            "PUT_ORDER_REQ_RECEIVED": cls.OPEN,
            "PARTIAL": cls.PARTIALLY_FILLED,
            "PARTIALLY_EXECUTED": cls.PARTIALLY_FILLED,
            "PARTIALLY_CANCELLED": cls.PARTIALLY_FILLED,
            # Upstox-specific
            "OPEN_ORDER": cls.OPEN,
            "TRIGGER_ORDER": cls.OPEN,
            "CANCEL_PENDING": cls.CANCELLED,
            "REJECTED_BY_BROKER": cls.REJECTED,
            "REJECTED_BY_EXCHANGE": cls.REJECTED,
            "MODIFIED": cls.OPEN,
            "MODIFIED_PENDING": cls.OPEN,
            "AFTER_MARKET_ORDER_REQ_RECEIVED": cls.OPEN,
            "AMO": cls.OPEN,
            "MARGIN_TRADED": cls.PARTIALLY_FILLED,
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
        """Return a new Position after applying a signed fill.

        ``quantity`` is the signed change (positive for a buy fill,
        negative for a sell fill). Average price is recomputed correctly
        for additions, partial closes, and side flips; realized PnL is
        updated for the closed portion.
        """
        old_qty = self.quantity
        old_avg = self.avg_price
        delta = quantity
        new_qty = old_qty + delta

        if old_qty == 0:
            new_avg = price
            new_realized = self.realized_pnl
        elif (old_qty > 0 and delta < 0) or (old_qty < 0 and delta > 0):
            # Opposite-side fill: realize PnL on the closed portion.
            closed = min(abs(old_qty), abs(delta))
            pnl_factor = Decimal("1") if old_qty > 0 else Decimal("-1")
            new_realized = self.realized_pnl + Decimal(str(closed)) * (price - old_avg) * pnl_factor
            if new_qty == 0:
                new_avg = Decimal("0")
            elif abs(delta) > abs(old_qty):
                # Net position flipped to the fill side.
                new_avg = price
            else:
                new_avg = old_avg
        else:
            # Same-side fill: weighted average price.
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

    bids: list[DepthLevel] | None = None
    asks: list[DepthLevel] | None = None

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
    """Canonical instrument master record."""

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


# ── Additional Domain Types (Upstox Sprint 6) ──────────────────────────


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
class MarketDepthLevel:
    """Single bid/ask level in an order book (alias-style name for Upstox)."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


@dataclass(slots=True, frozen=False)
class SliceOrderRequest:
    """Request for splitting a large order into child orders."""

    symbol: str = ""
    exchange: str = "NSE"
    side: Side = Side.BUY
    quantity: int = 0
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY


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


# ── Upstox compatibility aliases ──────────────────────────────────────────

TransactionType = Side  # Upstox uses TransactionType.BUY/SELL

# Import ExchangeSegment enum from enums.py (has .NSE, .BSE, .NSE_FNO etc.)
FeedMode = str          # Upstox uses string-based feed modes


# ── Upstox compatibility: enums from deprecated enums.py ──────────────────


class ExchangeSegment(str, Enum):
    """Exchange segments supported by the broker system.

    Migrated from brokers.common.core.domain. The values use the
    canonical wire-format strings (e.g. "NSE_EQ") so the segment
    string used in the HTTP payload matches what the broker expects.
    """

    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX = "MCXCOMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    IDX_I = "IDX_I"


class InstrumentType(str, Enum):
    """Canonical instrument type categories."""

    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"


# FeedMode is a string-based enum (LTP, QUOTE, FULL, etc.) — keep
# as a simple str alias for now; future refactor can make it a
# proper Enum. Matches the value of brokers.common.core.enums.FeedMode.
FeedMode = str


# ── Upstox compatibility: input shapes from deprecated models.py ──────


@dataclass(slots=True, frozen=False)
class OrderRequest:
    """Input model for placing an order.

    Migrated from the deprecated Pydantic model in
    ``brokers.common.core.models``. Same fields and semantics, but as
    a lightweight dataclass — no Pydantic validation overhead.
    """

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


@dataclass(slots=True, frozen=False)
class ModifyOrderRequest:
    """Input model for modifying an existing order."""

    order_id: str
    quantity: int | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: OrderType | None = None
    validity: Validity | None = None
    product_type: ProductType | None = None


@dataclass(slots=True, frozen=False)
class OrderPreview:
    """Outcome of pre-flight order validation."""

    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notional: Decimal | None = None
    margin_required: Decimal | None = None


@dataclass(slots=True, frozen=False)
class HistoricalCandle:
    """A single OHLCV candle returned by the historical-data endpoint."""

    timestamp: datetime | None = None
    symbol: str = ""
    exchange: str = "NSE"
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    open_interest: int = 0
    timeframe: str = "1D"


# ── Upstox compatibility: from deprecated connection.py ────────────────────


class Capability(str, Enum):
    """Capabilities a broker connection can provide (Upstox compat)."""

    MARKET_DATA = "market_data"
    ORDER_COMMAND = "order_command"
    ORDER_QUERY = "order_query"
    PORTFOLIO = "portfolio"
    OPTIONS_CHAIN = "options_chain"
    INSTRUMENTS = "instruments"
    FUTURES = "futures"
    HISTORICAL_DATA = "historical_data"
    WEBSOCKET = "websocket"
    BRACKET_ORDER = "bracket_order"
    COVER_ORDER = "cover_order"
    GTT_ORDER = "gtt_order"
    SLICE_ORDER = "slice_order"
    MARGIN = "margin"
    NEWS = "news"
    SESSION_RISK = "session_risk"
    ALERTS = "alerts"
    MARKET_STATUS = "market_status"
    DEPTH = "depth"
    ORDER_STREAM = "order_stream"
    IDEMPOTENCY = "idempotency"
    MULTI_ORDER = "multi_order"
    KILL_SWITCH = "kill_switch"
    STATIC_IP = "static_ip"
    SMARTLIST = "smartlist"
    FII_DII = "fii_dii"
    OI_PCR_MAXPAIN = "oi_pcr_maxpain"
    MARKET_INTELLIGENCE = "market_intelligence"
    FUNDAMENTALS = "fundamentals"
    IPO = "ipo"
    MUTUAL_FUNDS = "mutual_funds"
    PAYMENTS = "payments"
    INSTRUMENT_SEARCH = "instrument_search"
    HISTORICAL_TRADES = "historical_trades"
    TSL = "trailing_stop_loss"
    MTF = "mtf"
    WEBHOOKS = "webhooks"
    PORTFOLIO_STREAM = "portfolio_stream"
    ORDER_SLICING = "order_slicing"
    DEPTH_30 = "depth_30"
    LEVEL2_MARKET_DATA = "level2_market_data"
    OPTION_GREEKS = "option_greeks"
    GLOBAL_MARKETS = "global_markets"
    VOLATILITY_INDEX = "volatility_index"


class ConnectionStatus(str, Enum):
    """Lifecycle status of a broker connection (Upstox compat)."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"

    def is_connected(self) -> bool:
        return self == ConnectionStatus.CONNECTED


class BrokerConnection(ABC):
    """Abstract broker connection with capability-based service discovery.

    Migrated from brokers.common.core.domain. New broker adapters
    should use the MarketDataGateway ABC from brokers.common.gateway
    directly; this class is retained for Upstox backward compatibility.

    Subclasses register providers in ``_capability_map`` during init.
    Consumers discover services at runtime::

        conn = SomeBrokerConnection(...)
        if conn.has_capability(Capability.MARKET_DATA):
            md_provider = conn.get_capability(Capability.MARKET_DATA)
            quote = md_provider.get_quote("2885")
    """

    def __init__(
        self,
        name: str,
        broker_id: str,
        capabilities: set[Capability] | None = None,
    ):
        self._name = name
        self._broker_id = broker_id
        self._capabilities: set[Capability] = capabilities or set()
        self._capability_map: dict[Capability, Any] = {}
        self._status: ConnectionStatus = ConnectionStatus.DISCONNECTED

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the broker."""
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """Tear down the broker connection."""
        ...

    @abstractmethod
    def reconnect(self) -> bool:
        """Re-establish a dropped connection."""
        ...

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    def capabilities(self) -> set[Capability]:
        return set(self._capabilities)

    def has_capability(self, capability: Capability) -> bool:
        return capability in self._capabilities

    def get_capability(self, capability: Capability):
        return self._capability_map.get(capability)

    def _register_capability(self, capability: Capability, provider: Any) -> None:
        self._capabilities.add(capability)
        self._capability_map[capability] = provider

    def _set_status(self, status: ConnectionStatus) -> None:
        self._status = status

    def __enter__(self) -> BrokerConnection:
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()
