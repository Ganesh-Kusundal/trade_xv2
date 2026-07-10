"""Analytics Strategy Pipeline — Protocol, Models, and Pipeline.

Public API:
    Signal, SignalType, StrategyResult
    Strategy (Protocol)
    StrategyPipeline, MomentumStrategy, BreakoutStrategy
"""

from analytics.strategy.models import Signal, SignalType, StrategyResult
from analytics.strategy.pipeline import BreakoutStrategy, MomentumStrategy, StrategyPipeline
from analytics.strategy.protocols import Strategy

__all__ = [
    "BreakoutStrategy",
    "MomentumStrategy",
    "Signal",
    "SignalType",
    "Strategy",
    "StrategyPipeline",
    "StrategyResult",
]
