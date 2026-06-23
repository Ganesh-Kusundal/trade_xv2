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
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field, field_validator, model_validator

# ── Generic Response Wrapper ─────────────────────────────────────────────────

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response for list endpoints."""
    items: List[T]
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
    trace_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = False
    error: ErrorDetail
    timestamp: datetime = Field(default_factory=datetime.now)


# ── Symbol & Instrument Schemas ──────────────────────────────────────────────

class SymbolSearchRequest(BaseModel):
    """Symbol search query parameters."""
    q: str = Field(..., description="Search query", min_length=1, max_length=50)
    exchange: Optional[str] = Field(None, description="Filter by exchange (NSE, BSE, MCX)")
    limit: int = Field(25, ge=1, le=100, description="Max results")


class SymbolInfo(BaseModel):
    """Complete symbol metadata."""
    symbol: str
    exchange: str
    name: Optional[str] = None
    segment: Optional[str] = None
    isin: Optional[str] = None
    lot_size: int = 1
    tick_size: float = 0.05
    sector: Optional[str] = None
    instrument_type: str = "EQUITY"
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    total_rows: int = 0


class SymbolSearchResponse(BaseModel):
    """Symbol search results."""
    results: List[SymbolInfo]
    count: int


class UniverseResponse(BaseModel):
    """Universe symbol list."""
    name: str
    symbols: List[str]
    count: int


# ── Market Data Schemas ──────────────────────────────────────────────────────

class CandleRequest(BaseModel):
    """Candle query parameters."""
    symbol: str = Field(..., description="Symbol to fetch")
    timeframe: str = Field(..., description="Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)")
    from_ts: Optional[int] = Field(None, description="Start timestamp (ms)")
    to_ts: Optional[int] = Field(None, description="End timestamp (ms)")
    limit: int = Field(200, ge=1, le=5000, description="Max candles")


class Candle(BaseModel):
    """OHLCV candle."""
    t: int = Field(..., description="Timestamp (ms)")
    o: float = Field(..., description="Open")
    h: float = Field(..., description="High")
    l: float = Field(..., description="Low")
    c: float = Field(..., description="Close")
    v: float = Field(..., description="Volume")
    oi: float = Field(0, description="Open interest")


class CandlesResponse(BaseModel):
    """Candle data response."""
    symbol: str
    timeframe: str
    exchange: str = "NSE"
    candles: List[Candle]
    count: int


class QuoteResponse(BaseModel):
    """Latest quote/LTP snapshot."""
    symbol: str
    exchange: str
    ltp: float
    timestamp: int = Field(..., description="Timestamp (ms)")
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_qty: Optional[float] = None
    ask_qty: Optional[float] = None
    volume: Optional[float] = None
    oi: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None


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
    metadata: Optional[dict[str, Any]] = None


class IndicatorsResponse(BaseModel):
    """Indicator values response."""
    symbol: str
    indicator_type: str
    values: List[IndicatorValue]
    count: int


class ScannerSnapshot(BaseModel):
    """Intraday scanner snapshot for a symbol."""
    symbol: str
    ltp: float
    intraday_score: float
    signal: str  # BUY, SELL, BREAKOUT, NEUTRAL
    trend: str  # Bullish, Bearish, Neutral
    rsi_14: Optional[float] = None
    roc_5: Optional[float] = None
    relative_volume: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    day_volume: Optional[float] = None


class ScannerCandidatesResponse(BaseModel):
    """Top scanner candidates."""
    candidates: List[ScannerSnapshot]
    count: int
    timestamp: datetime = Field(default_factory=datetime.now)


class RelativeStrengthResponse(BaseModel):
    """Relative strength rankings."""
    rankings: List[dict[str, Any]]
    count: int


class MarketBreadthResponse(BaseModel):
    """Market breadth indicators."""
    advances: float
    declines: float
    unchanged: float
    advance_decline_ratio: float
    new_highs: float
    new_lows: float
    trin: Optional[float] = None
    mcclellan_oscillator: Optional[float] = None
    breadth_score: float
    regime: str  # Positive, Negative, Neutral


# ── Strategy Schemas ─────────────────────────────────────────────────────────

class StrategySignal(BaseModel):
    """Strategy signal."""
    symbol: str
    timestamp: int
    signal_type: str  # STRONG_BUY, BUY, SELL, STRONG_SELL, NEUTRAL
    score: float
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    entry_level: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None


class StrategySignalsResponse(BaseModel):
    """Strategy signals response."""
    signals: List[StrategySignal]
    count: int


# ── Options Schemas ──────────────────────────────────────────────────────────

class PCRResponse(BaseModel):
    """Put-Call Ratio data."""
    timestamp: int
    underlying: str
    expiry_kind: str  # WEEK, MONTH
    expiry_date: str
    spot: float
    pcr_volume: Optional[float] = None
    pcr_oi: Optional[float] = None
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
    put_call_iv_ratio: Optional[float] = None
    days_to_expiry: int


class OptionContract(BaseModel):
    """Single option contract with Greeks.
    
    Note: bid/ask are only available from live market data feeds, not from
    historical OHLCV parquet files. They will be None for historical data.
    iv/delta/gamma/theta/vega require Option Greeks pricing from broker API.
    """
    symbol: str
    expiry: str
    strike: float
    option_type: str  # CE or PE
    ltp: float
    bid: Optional[float] = None  # Requires live market depth; None for historical data
    ask: Optional[float] = None  # Requires live market depth; None for historical data
    volume: float
    oi: float
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None


class OptionChainResponse(BaseModel):
    """Option chain response."""
    underlying: str
    expiry: str
    contracts: List[OptionContract]
    count: int


# ── Replay Schemas ───────────────────────────────────────────────────────────

class CreateReplaySessionRequest(BaseModel):
    """Create replay session request."""
    symbol: str
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    timeframe: str = "1m"
    from_t: Optional[int] = None
    to_t: Optional[int] = None
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
    n: Optional[int] = Field(None, description="Steps for 'step' action")
    to_t: Optional[int] = Field(None, description="Target timestamp for 'seek'")
    speed: Optional[int] = Field(None, description="Speed multiplier for 'set_speed'")


# ── Backtest Schemas ─────────────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    """Backtest execution request."""
    symbol: str
    years: int = Field(1, ge=1, le=10)
    timeframe: str = "1d"
    initial_capital: float = 100_000
    strategy: str = Field(..., description="Strategy name")


class BacktestMetrics(BaseModel):
    """Backtest performance metrics."""
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
    """Backtest result."""
    run_id: str
    symbol: str
    timeframe: str
    metrics: BacktestMetrics
    trades: Optional[List[dict[str, Any]]] = None


# ── Portfolio & Order Schemas ────────────────────────────────────────────────

class PositionResponse(BaseModel):
    """Position data."""
    symbol: str
    exchange: str
    quantity: float
    average_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    pnl_pct: float


class PositionListResponse(BaseModel):
    """All positions."""
    positions: List[PositionResponse]
    total_pnl: float
    total_exposure: float


class OrderRequest(BaseModel):
    """Place order request with comprehensive validation."""
    symbol: str = Field(..., min_length=1, max_length=50, description="Trading symbol (e.g., RELIANCE, RELIANCE-EQ)")
    exchange: str = Field(..., description="Exchange: NSE, BSE, NFO, CDS, MCX")
    transaction_type: str = Field(..., description="BUY or SELL")
    order_type: str = Field(..., description="MARKET, LIMIT, SL, SL-M")
    quantity: int = Field(..., ge=1, le=1000000, description="Order quantity (must be > 0 and <= 1M)")
    price: Optional[float] = Field(None, ge=0.01, le=1000000, description="Price for LIMIT/SL orders")
    trigger_price: Optional[float] = Field(None, ge=0.01, le=1000000, description="Trigger price for SL/SL-M orders")
    product_type: str = Field("INTRADAY", description="INTRADAY, DELIVERY, MARGIN, CO, BO")

    @field_validator('transaction_type')
    @classmethod
    def validate_transaction_type(cls, v: str) -> str:
        """Validate transaction type is BUY or SELL."""
        if v.upper() not in ('BUY', 'SELL'):
            raise ValueError('transaction_type must be BUY or SELL')
        return v.upper()

    @field_validator('exchange')
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        """Validate exchange is a supported Indian exchange."""
        valid_exchanges = {'NSE', 'BSE', 'NFO', 'CDS', 'MCX', 'BCD'}
        if v.upper() not in valid_exchanges:
            raise ValueError(f'exchange must be one of: {valid_exchanges}')
        return v.upper()

    @field_validator('order_type')
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        """Validate order type is supported."""
        valid_types = {'MARKET', 'LIMIT', 'SL', 'SL-M'}
        if v.upper() not in valid_types:
            raise ValueError(f'order_type must be one of: {valid_types}')
        return v.upper()

    @field_validator('product_type')
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        """Validate product type is supported."""
        valid_products = {'INTRADAY', 'DELIVERY', 'MARGIN', 'CO', 'BO'}
        if v.upper() not in valid_products:
            raise ValueError(f'product_type must be one of: {valid_products}')
        return v.upper()

    @model_validator(mode='after')
    def validate_order_constraints(self) -> 'OrderRequest':
        """Validate cross-field constraints for order types."""
        order_type = self.order_type.upper()

        # LIMIT and SL orders require price
        if order_type in ('LIMIT', 'SL'):
            if self.price is None or self.price <= 0:
                raise ValueError('price is required and must be > 0 for LIMIT/SL orders')

        # SL and SL-M orders require trigger_price
        if order_type in ('SL', 'SL-M'):
            if self.trigger_price is None or self.trigger_price <= 0:
                raise ValueError('trigger_price is required and must be > 0 for SL/SL-M orders')

        # For SL orders, validate price vs trigger_price relationship
        if order_type == 'SL' and self.price and self.trigger_price:
            if self.transaction_type.upper() == 'BUY':
                if self.price < self.trigger_price:
                    raise ValueError('for SL BUY orders, price must be >= trigger_price')
            else:  # SELL
                if self.price > self.trigger_price:
                    raise ValueError('for SL SELL orders, price must be <= trigger_price')

        return self


class OrderResponse(BaseModel):
    """Order data."""
    order_id: str
    symbol: str
    exchange: str
    transaction_type: str
    order_type: str
    quantity: int
    price: Optional[float] = None
    status: str
    filled_quantity: int = 0
    average_price: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class OrderListResponse(BaseModel):
    """All orders."""
    orders: List[OrderResponse]
    count: int


class Position(BaseModel):
    """Simplified position model."""
    symbol: str
    exchange: str
    quantity: float
    average_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    pnl_pct: float


class PositionsResponse(BaseModel):
    """All positions response."""
    positions: List[Position]
    count: int
    total_pnl: float
    total_pnl_percent: float


class Holding(BaseModel):
    """Holding model."""
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    current_price: float
    invested_value: float
    current_value: float
    pnl: float
    pnl_percent: float


class HoldingsResponse(BaseModel):
    """All holdings response."""
    holdings: List[Holding]
    count: int
    total_value: float
    total_invested: float
    total_pnl: float


class PortfolioSummary(BaseModel):
    """Portfolio summary."""
    total_value: float
    total_invested: float
    total_pnl: float
    total_pnl_percent: float
    realized_pnl: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    positions_count: int
    holdings_count: int


class Trade(BaseModel):
    """Trade execution model."""
    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    transaction_type: str
    quantity: int
    price: float
    timestamp: datetime


class TradesResponse(BaseModel):
    """All trades response."""
    trades: List[Trade]
    count: int


class OrdersResponse(BaseModel):
    """All orders response (alias for OrderListResponse)."""
    orders: List[OrderResponse]
    count: int


# Backwards compatibility aliases
Order = OrderResponse


# ── Health & Status Schemas ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)
    services: Optional[dict[str, str]] = None


class ReadinessResponse(BaseModel):
    """Readiness probe response."""
    ready: bool
    checks: dict[str, bool]
    timestamp: datetime = Field(default_factory=datetime.now)
