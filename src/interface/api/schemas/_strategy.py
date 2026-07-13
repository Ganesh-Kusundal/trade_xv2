"""Strategy schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
