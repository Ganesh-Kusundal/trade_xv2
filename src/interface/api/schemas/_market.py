"""Market Data schemas (Candles, Quotes)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.value_objects.money import MoneyField


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
