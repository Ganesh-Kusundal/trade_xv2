"""Backtest schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.backtest.models import BacktestMetrics, BacktestResultResponse


class BacktestRunRequest(BaseModel):
    """Backtest execution request."""

    symbol: str
    years: int = Field(1, ge=1, le=10)
    timeframe: str = "1d"
    initial_capital: float = 100_000
    strategy: str = Field(..., description="Strategy name")


__all__ = ["BacktestMetrics", "BacktestResultResponse", "BacktestRunRequest"]
