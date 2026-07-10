"""Analytics Backtest Engine — replay with rich performance analytics.

Public API:
    BacktestConfig, BacktestResult, BacktestEngine
    PerformanceMetrics, TradeAnalysis
    FastBacktestEngine (research-oriented; has look-ahead bias warning)
"""

from analytics.backtest.engine import BacktestEngine, ResearchMode
from analytics.backtest.fast_backtest import FastBacktestEngine
from analytics.backtest.models import (
    BacktestConfig,
    BacktestResult,
    PerformanceMetrics,
    TradeAnalysis,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "FastBacktestEngine",
    "PerformanceMetrics",
    "ResearchMode",
    "TradeAnalysis",
]
