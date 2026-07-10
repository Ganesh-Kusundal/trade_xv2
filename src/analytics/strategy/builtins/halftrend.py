"""HalfTrend strategy wrapper.

Registers HalfTrendStrategy from analytics.indicators.halftrend_backtest
with the canonical name "halftrend" in the StrategyRegistry.

This wrapper enables HalfTrend to be discovered alongside other built-in
strategies via StrategyRegistry.discover().
"""

from analytics.indicators.halftrend_backtest import HalfTrendStrategy as _HalfTrendStrategy
from analytics.strategy.registry import StrategyRegistry

# Re-register with canonical name
StrategyRegistry.register("halftrend", _HalfTrendStrategy)
