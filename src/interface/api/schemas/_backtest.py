"""Backtest schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    trades: list[dict[str, Any]] | None = None
    research_mode: str = "pure_sim"
    research_only: bool = True
