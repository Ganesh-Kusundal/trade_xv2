"""Analytics Backtest Engine — replay with rich performance analytics.

Public API:
    BacktestConfig, BacktestResult, BacktestEngine
    PerformanceMetrics, TradeAnalysis
"""

from analytics.backtest.engine import BacktestEngine
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
    "PerformanceMetrics",
    "TradeAnalysis",
]
