"""Pydantic schemas for all API request/response types.

Defines typed contracts for:
- Symbols & Instruments
- Market Data (Candles, Quotes)
- Analytics (Indicators, Scanner Results)
- Strategy Signals
- Options Analytics
- Replay Sessions
- Backtest Results
- Portfolio & Orders
- Error Responses

NOTE (P2-3): Some schemas here (OrderRequest, OrderResponse, Trade) parallel
definitions in ``domain/entities/order.py`` and ``domain/requests.py``.
The domain entities are canonical; API schemas are serialization adapters.
When modifying order/trade fields, update ALL THREE locations:
  1. ``domain/entities/order.py`` — canonical domain model
  2. ``domain/requests.py`` — canonical request objects
  3. ``api/schemas.py`` — API serialization layer (this file)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from domain.value_objects.money import MoneyField

# ── Generic Response Wrapper ─────────────────────────────────────────────────

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    success: bool = True
    data: T | None = None
    message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response for list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size > 0 else 0


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str
    message: str
    trace_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    error: ErrorDetail
    timestamp: datetime = Field(default_factory=datetime.now)


# ── Symbol & Instrument Schemas ──────────────────────────────────────────────


class SymbolSearchRequest(BaseModel):
    """Symbol search query parameters."""

    q: str = Field(..., description="Search query", min_length=1, max_length=50)
    exchange: str | None = Field(None, description="Filter by exchange (NSE, BSE, MCX)")
    limit: int = Field(25, ge=1, le=100, description="Max results")


class SymbolInfo(BaseModel):
    """Complete symbol metadata."""

    symbol: str
    exchange: str
    name: str | None = None
    segment: str | None = None
    isin: str | None = None
    lot_size: int = 1
    tick_size: float = 0.05
    sector: str | None = None
    instrument_type: str = "EQUITY"
    first_date: str | None = None
    last_date: str | None = None
    total_rows: int = 0


class SymbolSearchResponse(BaseModel):
    """Symbol search results."""

    results: list[SymbolInfo]
    count: int


class UniverseResponse(BaseModel):
    """Universe symbol list."""

    name: str
    symbols: list[str]
    count: int


# ── Market Data Schemas ──────────────────────────────────────────────────────


class CandleRequest(BaseModel):
    """Candle query parameters."""

    symbol: str = Field(..., description="Symbol to fetch")
    timeframe: str = Field(..., description="Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)")
    from_ts: int | None = Field(None, description="Start timestamp (ms)")
    to_ts: int | None = Field(None, description="End timestamp (ms)")
    limit: int = Field(200, ge=1, le=5000, description="Max candles")


class Candle(BaseModel):
    """OHLCV candle."""

    t: int = Field(..., description="Timestamp (ms)")
    o: MoneyField = Field(..., description="Open")
    h: MoneyField = Field(..., description="High")
    l: MoneyField = Field(..., description="Low")
    c: MoneyField = Field(..., description="Close")
    v: float = Field(..., description="Volume")
    oi: float = Field(0, description="Open interest")


class CandlesResponse(BaseModel):
    """Candle data response."""

    symbol: str
    timeframe: str
    exchange: str = "NSE"
    candles: list[Candle]
    count: int


class QuoteResponse(BaseModel):
    """Latest quote/LTP snapshot."""

    symbol: str
    exchange: str
    ltp: MoneyField
    timestamp: int = Field(..., description="Timestamp (ms)")
    bid: MoneyField | None = None
    ask: MoneyField | None = None
    bid_qty: float | None = None
    ask_qty: float | None = None
    volume: float | None = None
    oi: float | None = None
    open: MoneyField | None = None
    high: MoneyField | None = None
    low: MoneyField | None = None
    close: MoneyField | None = None


# ── Analytics Schemas ────────────────────────────────────────────────────────


class IndicatorRequest(BaseModel):
    """Indicator query parameters."""

    symbol: str
    type: str = Field(..., description="Indicator type (atr, vwap, rsi, momentum, volume)")
    timeframe: str = "1m"
    limit: int = Field(100, ge=1, le=1000)


class IndicatorValue(BaseModel):
    """Single indicator value."""

    timestamp: int
    symbol: str
    value: float
    metadata: dict[str, Any] | None = None


class IndicatorsResponse(BaseModel):
    """Indicator values response."""

    symbol: str
    indicator_type: str
    values: list[IndicatorValue]
    count: int


class ScannerSnapshot(BaseModel):
    """Intraday scanner snapshot for a symbol."""

    symbol: str
    ltp: float
    intraday_score: float
    signal: str  # BUY, SELL, BREAKOUT, NEUTRAL
    trend: str  # Bullish, Bearish, Neutral
    rsi_14: float | None = None
    roc_5: float | None = None
    relative_volume: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    day_volume: float | None = None


class ScannerCandidatesResponse(BaseModel):
    """Top scanner candidates."""

    candidates: list[ScannerSnapshot]
    count: int
    timestamp: datetime = Field(default_factory=datetime.now)


class RelativeStrengthResponse(BaseModel):
    """Relative strength rankings."""

    rankings: list[dict[str, Any]]
    count: int


class MarketBreadthResponse(BaseModel):
    """Market breadth indicators."""

    advances: float
    declines: float
    unchanged: float
    advance_decline_ratio: float
    new_highs: float
    new_lows: float
    trin: float | None = None
    mcclellan_oscillator: float | None = None
    breadth_score: float
    regime: str  # Positive, Negative, Neutral


# ── Strategy Schemas ─────────────────────────────────────────────────────────


class StrategySignal(BaseModel):
    """Strategy signal."""

    symbol: str
    timestamp: int
    signal_type: str  # STRONG_BUY, BUY, SELL, STRONG_SELL, NEUTRAL
    score: float
    stop_loss: float | None = None
    target: float | None = None
    entry_level: float | None = None
    metadata: dict[str, Any] | None = None


class StrategySignalsResponse(BaseModel):
    """Strategy signals response."""

    signals: list[StrategySignal]
    count: int


# ── Options Schemas ──────────────────────────────────────────────────────────


class PCRResponse(BaseModel):
    """Put-Call Ratio data."""

    timestamp: int
    underlying: str
    expiry_kind: str  # WEEK, MONTH
    expiry_date: str
    spot: float
    pcr_volume: float | None = None
    pcr_oi: float | None = None
    total_ce_volume: float
    total_pe_volume: float
    total_ce_oi: float
    total_pe_oi: float


class MaxPainResponse(BaseModel):
    """Max Pain data."""

    timestamp: int
    underlying: str
    expiry_kind: str
    expiry_date: str
    spot: float
    max_pain_strike: float
    total_pain_at_max_pain: float
    distance_from_spot: float
    position_vs_spot: str  # below_spot, above_spot, at_spot


class IVSurfaceResponse(BaseModel):
    """IV surface data."""

    timestamp: int
    underlying: str
    expiry_kind: str
    expiry_date: str
    spot: float
    atm_strike: float
    atm_iv: float
    otm_put_iv: float
    otm_call_iv: float
    iv_skew: float
    put_call_iv_ratio: float | None = None
    days_to_expiry: int


class OptionContract(BaseModel):
    """Single option contract with Greeks.

    Note: bid/ask are only available from live market data feeds, not from
    historical OHLCV parquet files. They will be None for historical data.
    iv/delta/gamma/theta/vega require Option Greeks pricing from broker API.
    """

    symbol: str
    expiry: str
    strike: MoneyField
    option_type: str  # CE or PE
    ltp: MoneyField
    bid: MoneyField | None = None  # Requires live market depth; None for historical data
    ask: MoneyField | None = None  # Requires live market depth; None for historical data
    volume: float
    oi: float
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


class OptionChainResponse(BaseModel):
    """Option chain response."""

    underlying: str
    expiry: str
    contracts: list[OptionContract]
    count: int


# ── Replay Schemas ───────────────────────────────────────────────────────────


class CreateReplaySessionRequest(BaseModel):
    """Create replay session request."""

    symbol: str
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    timeframe: str = "1m"
    from_t: int | None = None
    to_t: int | None = None
    universe: str = "NIFTY500"
    speed: int = 5


class ReplaySessionResponse(BaseModel):
    """Replay session state."""

    session_id: str
    status: str  # initialized, playing, paused, stopped
    date: str
    universe: str = "NIFTY500"
    speed: int = 5
    progress: float = 0.0


class ReplayControlRequest(BaseModel):
    """Replay control action."""

    action: str = Field(..., description="play, pause, step, seek, set_speed")
    n: int | None = Field(None, description="Steps for 'step' action")
    to_t: int | None = Field(None, description="Target timestamp for 'seek'")
    speed: int | None = Field(None, description="Speed multiplier for 'set_speed'")


# ── Backtest Schemas ─────────────────────────────────────────────────────────


class BacktestRunRequest(BaseModel):
    """Backtest execution request."""

    symbol: str
    years: int = Field(1, ge=1, le=10)
    timeframe: str = "1d"
    initial_capital: float = 100_000
    strategy: str = Field(..., description="Strategy name")


class BacktestMetrics(BaseModel):
    """Backtest performance metrics.

    Canonical definition lives in ``domain.backtest.models``.
    Re-exported here for backward compatibility.
    """

    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int


class BacktestResultResponse(BaseModel):
    """Backtest result.

    Canonical definition lives in ``domain.backtest.models``.
    Re-exported here for backward compatibility.
    """

    run_id: str
    symbol: str
    timeframe: str
    metrics: BacktestMetrics
    trades: list[dict[str, Any]] | None = None


# ── Portfolio & Order Schemas ────────────────────────────────────────────────


class PositionResponse(BaseModel):
    """Position data."""

    symbol: str
    exchange: str
    quantity: int
    average_price: MoneyField
    current_price: MoneyField
    unrealized_pnl: MoneyField
    realized_pnl: MoneyField
    pnl_pct: float


class PositionListResponse(BaseModel):
    """All positions."""

    positions: list[PositionResponse]
    total_pnl: MoneyField
    total_exposure: MoneyField


class OrderRequest(BaseModel):
    """Place order request with comprehensive validation."""

    symbol: str = Field(
        ..., min_length=1, max_length=50, description="Trading symbol (e.g., RELIANCE, RELIANCE-EQ)"
    )
    exchange: str = Field(..., description="Exchange: NSE, BSE, NFO, CDS, MCX")
    transaction_type: str = Field(..., description="BUY or SELL")
    order_type: str = Field(..., description="MARKET, LIMIT, SL, SL-M")
    quantity: int = Field(
        ..., ge=1, le=1000000, description="Order quantity (must be > 0 and <= 1M)"
    )
    price: float | None = Field(None, ge=0.01, le=1000000, description="Price for LIMIT/SL orders")
    trigger_price: float | None = Field(
        None, ge=0.01, le=1000000, description="Trigger price for SL/SL-M orders"
    )
    product_type: str = Field("INTRADAY", description="INTRADAY, DELIVERY, MARGIN, CO, BO")
    correlation_id: str | None = Field(None, description="Optional correlation ID for tracing")

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, v: str) -> str:
        """Validate transaction type is BUY or SELL."""
        if v.upper() not in ("BUY", "SELL"):
            raise ValueError("transaction_type must be BUY or SELL")
        return v.upper()

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        """Validate exchange is a supported Indian exchange."""
        valid_exchanges = {"NSE", "BSE", "NFO", "CDS", "MCX", "BCD"}
        if v.upper() not in valid_exchanges:
            raise ValueError(f"exchange must be one of: {valid_exchanges}")
        return v.upper()

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        """Validate order type is supported."""
        valid_types = {"MARKET", "LIMIT", "SL", "SL-M"}
        if v.upper() not in valid_types:
            raise ValueError(f"order_type must be one of: {valid_types}")
        return v.upper()

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        """Validate product type is supported."""
        valid_products = {"INTRADAY", "DELIVERY", "MARGIN", "CO", "BO"}
        if v.upper() not in valid_products:
            raise ValueError(f"product_type must be one of: {valid_products}")
        return v.upper()

    @model_validator(mode="after")
    def validate_order_constraints(self) -> OrderRequest:
        """Validate cross-field constraints for order types."""
        order_type = self.order_type.upper()

        # LIMIT and SL orders require price
        if order_type in ("LIMIT", "SL") and (self.price is None or self.price <= 0):
            raise ValueError("price is required and must be > 0 for LIMIT/SL orders")

        # SL and SL-M orders require trigger_price
        if order_type in ("SL", "SL-M") and (self.trigger_price is None or self.trigger_price <= 0):
            raise ValueError("trigger_price is required and must be > 0 for SL/SL-M orders")

        # For SL orders, validate price vs trigger_price relationship
        if order_type == "SL" and self.price and self.trigger_price:
            if self.transaction_type.upper() == "BUY":
                if self.price < self.trigger_price:
                    raise ValueError("for SL BUY orders, price must be >= trigger_price")
            else:  # SELL
                if self.price > self.trigger_price:
                    raise ValueError("for SL SELL orders, price must be <= trigger_price")

        return self


class OrderResponse(BaseModel):
    """Order data."""

    order_id: str
    symbol: str
    exchange: str
    transaction_type: str
    order_type: str
    quantity: int
    price: MoneyField | None = None
    status: str
    filled_quantity: int = 0
    average_price: MoneyField | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class OrderListResponse(BaseModel):
    """All orders."""

    orders: list[OrderResponse]
    count: int


class Position(BaseModel):
    """Simplified position model."""

    symbol: str
    exchange: str
    quantity: int
    average_price: MoneyField
    current_price: MoneyField
    unrealized_pnl: MoneyField
    realized_pnl: MoneyField
    pnl_pct: float


class PositionsResponse(BaseModel):
    """All positions response."""

    positions: list[Position]
    count: int
    total_pnl: MoneyField
    total_pnl_percent: float


class Holding(BaseModel):
    """Holding model."""

    symbol: str
    exchange: str
    quantity: int
    average_price: MoneyField
    current_price: MoneyField
    invested_value: MoneyField
    current_value: MoneyField
    pnl: MoneyField
    pnl_percent: float


class HoldingsResponse(BaseModel):
    """All holdings response."""

    holdings: list[Holding]
    count: int
    total_value: MoneyField
    total_invested: MoneyField
    total_pnl: MoneyField


class PortfolioSummary(BaseModel):
    """Portfolio summary."""

    total_value: MoneyField
    total_invested: MoneyField
    total_pnl: MoneyField
    total_pnl_percent: float
    realized_pnl: MoneyField
    unrealized_pnl: MoneyField
    margin_used: MoneyField
    margin_available: MoneyField
    positions_count: int
    holdings_count: int


class TradeResponse(BaseModel):
    """Trade execution model."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    transaction_type: str
    quantity: int
    price: MoneyField
    timestamp: datetime


class TradesResponse(BaseModel):
    """All trades response."""

    trades: list[TradeResponse]
    count: int


class OrdersResponse(BaseModel):
    """All orders response (alias for OrderListResponse)."""

    orders: list[OrderResponse]
    count: int


# ── Health & Status Schemas ──────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)
    services: dict[str, str] | None = None


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    ready: bool
    checks: dict[str, bool]
    timestamp: datetime = Field(default_factory=datetime.now)
