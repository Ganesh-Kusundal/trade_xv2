"""Analytics schemas (Indicators, Scanner Results, Market Breadth)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    momentum_5d_pct: float | None = Field(
        default=None,
        description="5-day price change %; not RSI.",
    )
    rsi_14: float | None = Field(
        default=None,
        description="True RSI(14) when sourced from feature views; absent on intraday snapshot.",
    )
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
