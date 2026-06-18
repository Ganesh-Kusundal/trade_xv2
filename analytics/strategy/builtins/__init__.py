"""Built-in strategies auto-registration.

This package imports and registers all built-in strategies with the
StrategyRegistry, making them discoverable via:

    StrategyRegistry.discover("analytics.strategy.builtins")

Registered strategies:
    - momentum: MomentumStrategy (RSI + ROC based)
    - breakout: BreakoutStrategy (swing high/low breakout)
    - halftrend: HalfTrendStrategy (trend following)
"""

from analytics.strategy.pipeline import BreakoutStrategy, MomentumStrategy
from analytics.strategy.registry import StrategyRegistry

# Auto-register built-in strategies
StrategyRegistry.register("momentum", MomentumStrategy)
StrategyRegistry.register("breakout", BreakoutStrategy)
