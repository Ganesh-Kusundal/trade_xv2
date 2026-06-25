"""Backtest Engine models — BacktestConfig, BacktestResult, TradeAnalysis.

Wraps the ReplayEngine and adds rich performance analytics:
    - Sharpe, Sortino, Calmar ratios
    - Profit factor, expected value
    - Max consecutive wins/losses
    - Average win/loss, holding period
    - Benchmark comparison (alpha, beta, Information Ratio)
    - Trade analysis (entry/exit distribution, time-in-trade)

Usage:
    from analytics.backtest import BacktestEngine, BacktestConfig
    engine = BacktestEngine(pipeline, strategy)
    result = engine.run(data, benchmark_data)
    print(result.metrics)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from analytics.replay.models import ReplayConfig, ReplayResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BacktestConfig
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig(ReplayConfig):
    """Backtest configuration — extends ReplayConfig with backtest-specific options.

    Inherits all ReplayConfig fields (initial_capital, warmup_bars, slippage, etc.)
    and adds benchmark comparison and analysis options.
    """

    benchmark_symbol: str = "NIFTY"
    risk_free_rate: float = 0.065  # Annual risk-free rate (6.5% for India)
    annualization_factor: int = 252  # Trading days per year


# ---------------------------------------------------------------------------
# Trade Analysis
# ---------------------------------------------------------------------------


@dataclass
class TradeAnalysis:
    """Detailed analysis of all trades in a backtest."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_holding_bars: float = 0.0

    profit_factor: float = 0.0
    expected_value: float = 0.0
    payoff_ratio: float = 0.0

    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0

    trades_by_strategy: dict[str, int] = field(default_factory=dict)
    avg_entry_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Performance Metrics
# ---------------------------------------------------------------------------


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""

    # Return metrics
    total_return: float = 0.0
    total_return_pct: float = 0.0
    cagr: float = 0.0

    # Risk metrics
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration: int = 0  # bars

    # Risk-adjusted metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0

    # Benchmark comparison
    alpha: float = 0.0
    beta: float = 0.0
    benchmark_return: float = 0.0
    tracking_error: float = 0.0

    # Trade metrics
    trade_analysis: TradeAnalysis = field(default_factory=TradeAnalysis)


# ---------------------------------------------------------------------------
# BacktestResult
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """Full backtest output with replay data + performance analytics."""

    replay: ReplayResult = field(default_factory=ReplayResult)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    benchmark_data: pd.DataFrame | None = None
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, Any]:
        m = self.metrics
        ta = m.trade_analysis
        return {
            "bars_processed": self.replay.bars_processed,
            "total_trades": ta.total_trades,
            "win_rate": round(ta.win_rate * 100, 1),
            "profit_factor": round(ta.profit_factor, 2),
            "total_return_pct": round(m.total_return_pct, 2),
            "cagr": round(m.cagr * 100, 2),
            "sharpe_ratio": round(m.sharpe_ratio, 2),
            "sortino_ratio": round(m.sortino_ratio, 2),
            "calmar_ratio": round(m.calmar_ratio, 2),
            "max_drawdown_pct": round(m.max_drawdown_pct * 100, 2),
            "max_drawdown_duration": m.max_drawdown_duration,
            "volatility": round(m.volatility * 100, 2),
            "alpha": round(m.alpha * 100, 2),
            "beta": round(m.beta, 2),
            "information_ratio": round(m.information_ratio, 2),
            "final_equity": round(self.replay.final_equity, 2),
            "avg_holding_bars": round(ta.avg_holding_bars, 1),
            "max_consecutive_wins": ta.max_consecutive_wins,
            "max_consecutive_losses": ta.max_consecutive_losses,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Convert summary to a single-row DataFrame."""
        return pd.DataFrame([self.summary])
