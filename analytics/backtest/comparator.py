"""Backtest comparison — compare multiple backtest results side by side."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.pipeline.features import ATR, ROC, RSI, SMA, Momentum, Trend
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.strategy import BreakoutStrategy, MomentumStrategy, StrategyPipeline


@dataclass
class ComparisonResult:
    """Side-by-side comparison of multiple backtests."""

    results: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> pd.DataFrame:
        """Return comparison as a DataFrame."""
        return pd.DataFrame(self.results)

    @property
    def best(self) -> dict | None:
        """Return the best result by Sharpe ratio."""
        if not self.results:
            return None
        return max(self.results, key=lambda x: x.get("sharpe_ratio", 0))


def compare_strategies(
    data: pd.DataFrame,
    symbol: str = "COMPARE",
    strategies: list[str] | None = None,
    initial_capital: float = 100_000,
    warmup_bars: int = 50,
) -> ComparisonResult:
    """Compare different strategies on the same data.

    Args:
        data: OHLCV DataFrame
        symbol: Symbol name
        strategies: List of strategy names to compare (default: ["momentum", "breakout"])
        initial_capital: Starting capital
        warmup_bars: Warmup period

    Returns:
        ComparisonResult with side-by-side comparison
    """
    if strategies is None:
        strategies = ["momentum", "breakout"]

    strategy_classes = {
        "momentum": MomentumStrategy,
        "breakout": BreakoutStrategy,
    }

    pipeline = (
        FeaturePipeline()
        .add(RSI(period=14))
        .add(ATR(period=14))
        .add(SMA(period=20))
        .add(ROC(period=5))
        .add(Momentum(period=5))
        .add(Trend(fast_period=10, slow_period=50))
    )

    config = BacktestConfig(initial_capital=initial_capital, warmup_bars=warmup_bars)
    result = ComparisonResult()

    for strategy_name in strategies:
        strategy_class = strategy_classes.get(strategy_name)
        if not strategy_class:
            continue

        strategy = StrategyPipeline(strategies=[strategy_class()])
        engine = BacktestEngine(pipeline, strategy, config)
        bt_result = engine.run(data, symbol=symbol)

        m = bt_result.metrics
        result.results.append({
            "strategy": strategy_name,
            "total_return_pct": m.total_return_pct,
            "cagr": m.cagr,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "max_drawdown_pct": m.max_drawdown_pct,
            "total_trades": m.trade_analysis.total_trades,
            "win_rate": m.trade_analysis.win_rate,
            "profit_factor": m.trade_analysis.profit_factor,
            "avg_win": m.trade_analysis.avg_win,
            "avg_loss": m.trade_analysis.avg_loss,
        })

    return result


def compare_parameters(
    data: pd.DataFrame,
    symbol: str = "COMPARE",
    param_sets: list[dict] | None = None,
    initial_capital: float = 100_000,
    warmup_bars: int = 50,
) -> ComparisonResult:
    """Compare different parameter sets for the same strategy.

    Args:
        data: OHLCV DataFrame
        symbol: Symbol name
        param_sets: List of parameter dicts, e.g. [{"rsi_period": 14}, {"rsi_period": 21}]
        initial_capital: Starting capital
        warmup_bars: Warmup period

    Returns:
        ComparisonResult with side-by-side comparison
    """
    if param_sets is None:
        param_sets = [
            {"rsi_period": 7, "sma_period": 10},
            {"rsi_period": 14, "sma_period": 20},
            {"rsi_period": 21, "sma_period": 30},
        ]

    config = BacktestConfig(initial_capital=initial_capital, warmup_bars=warmup_bars)
    result = ComparisonResult()

    for i, params in enumerate(param_sets):
        pipeline = (
            FeaturePipeline()
            .add(RSI(period=params.get("rsi_period", 14)))
            .add(ATR(period=params.get("atr_period", 14)))
            .add(SMA(period=params.get("sma_period", 20)))
            .add(ROC(period=params.get("roc_period", 5)))
            .add(Momentum(period=params.get("momentum_period", 5)))
            .add(Trend(
                fast_period=params.get("trend_fast", 10),
                slow_period=params.get("trend_slow", 50),
            ))
        )

        strategy = StrategyPipeline(strategies=[MomentumStrategy()])
        engine = BacktestEngine(pipeline, strategy, config)
        bt_result = engine.run(data, symbol=symbol)

        m = bt_result.metrics
        result.results.append({
            "params": params,
            "total_return_pct": m.total_return_pct,
            "cagr": m.cagr,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "max_drawdown_pct": m.max_drawdown_pct,
            "total_trades": m.trade_analysis.total_trades,
            "win_rate": m.trade_analysis.win_rate,
            "profit_factor": m.trade_analysis.profit_factor,
        })

    return result
