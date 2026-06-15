"""Paper Trading Engine — same pipeline as live, simulated fills.

Usage:
    from analytics.paper import PaperTradingEngine, PaperConfig
    from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
    from analytics.strategy import StrategyPipeline, MomentumStrategy

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = PaperConfig(initial_capital=100_000)

    engine = PaperTradingEngine(pipeline, strategy, config)
    result = engine.run(dataframe, symbol="RELIANCE")
    print(result.summary)
"""

from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import (
    PaperConfig,
    PaperOrder,
    PaperPosition,
    PaperResult,
    PaperSession,
    PaperTrade,
)

__all__ = [
    "PaperTradingEngine",
    "PaperConfig",
    "PaperSession",
    "PaperResult",
    "PaperOrder",
    "PaperPosition",
    "PaperTrade",
]
