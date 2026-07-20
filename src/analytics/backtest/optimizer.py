"""Strategy parameter optimization — grid search over parameter space."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import product

import pandas as pd

from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.pipeline.features import ATR, ROC, RSI, SMA, Momentum, Trend
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.strategy import StrategyPipeline
from domain.constants import ATR_PERIOD_DEFAULT, RSI_PERIOD_DEFAULT, SMA_WINDOW_DEFAULT

logger = logging.getLogger(__name__)


@dataclass
class ParamGrid:
    """Parameter grid for optimization."""

    name: str
    values: list[int | float | str]


@dataclass
class OptimizationResult:
    """Result of parameter optimization."""

    param_name: str
    param_values: list[int | float | str]
    results: list[dict] = field(default_factory=list)
    best_params: dict = field(default_factory=dict)
    best_return: float = 0.0
    best_sharpe: float = 0.0

    @property
    def summary(self) -> pd.DataFrame:
        """Return results as a DataFrame for easy analysis."""
        return pd.DataFrame(self.results)


def build_pipeline(
    rsi_period: int = RSI_PERIOD_DEFAULT,
    atr_period: int = ATR_PERIOD_DEFAULT,
    sma_period: int = SMA_WINDOW_DEFAULT,
    roc_period: int = 5,
    momentum_period: int = 5,
    trend_fast: int = 10,
    trend_slow: int = 50,
) -> FeaturePipeline:
    """Build a feature pipeline with configurable parameters."""
    return (
        FeaturePipeline()
        .add(RSI(period=rsi_period))
        .add(ATR(period=atr_period))
        .add(SMA(period=sma_period))
        .add(ROC(period=roc_period))
        .add(Momentum(period=momentum_period))
        .add(Trend(fast_period=trend_fast, slow_period=trend_slow))
    )


def optimize_grid(
    data: pd.DataFrame,
    symbol: str = "OPTIMIZE",
    param_grids: list[ParamGrid] | None = None,
    strategy_name: str = "momentum",
    initial_capital: float = 100_000,
    warmup_bars: int = 50,
    top_n: int = 10,
    trading_context: object | None = None,
) -> OptimizationResult:
    """Run grid search optimization over parameter space.

    Args:
        data: OHLCV DataFrame
        symbol: Symbol name for the backtest
        param_grids: List of ParamGrid objects defining the search space
        strategy_name: Strategy to optimize ("momentum" or "breakout")
        initial_capital: Starting capital
        warmup_bars: Warmup period
        top_n: Number of top results to keep
        trading_context: Optional TradingContext. Grid search always runs PURE_SIM
            (OMS overhead across hundreds of combos is real cost). When provided,
            the winning parameter set is re-run once in ResearchMode.PARITY as a
            confirmation against the real OMS path.

    Returns:
        OptimizationResult with all results and best parameters
    """
    from analytics.backtest.engine import ResearchMode
    from analytics.strategy import BreakoutStrategy, MomentumStrategy

    if param_grids is None:
        # Default grid: sweep all 7 parameters that compare_parameters uses.
        # Previously only swept 2 (rsi_period, sma_period).
        param_grids = [
            ParamGrid("rsi_period", [7, 14, 21]),
            ParamGrid("atr_period", [7, 14, 21]),
            ParamGrid("sma_period", [10, 20, 50]),
            ParamGrid("roc_period", [3, 5, 10]),
            ParamGrid("momentum_period", [3, 5, 10]),
            ParamGrid("trend_fast", [5, 10, 20]),
            ParamGrid("trend_slow", [30, 50, 100]),
        ]

    # Generate all parameter combinations
    param_names = [g.name for g in param_grids]
    param_values = [g.values for g in param_grids]
    combinations = list(product(*param_values))

    logger.info("Optimizing %d parameter combinations", len(combinations))
    if len(combinations) > 500:
        logger.warning(
            "Large parameter space (%d combinations). This may take a long time. "
            "Consider passing a smaller param_grids list for faster iteration.",
            len(combinations),
        )

    result = OptimizationResult(
        param_name=",".join(param_names),
        param_values=[str(c) for c in combinations],
    )

    best_return = -float("inf")
    best_sharpe = -float("inf")
    best_params = {}

    strategies = {
        "momentum": MomentumStrategy,
        "breakout": BreakoutStrategy,
    }
    strategy_class = strategies.get(strategy_name, MomentumStrategy)

    for combo in combinations:
        params = dict(zip(param_names, combo, strict=False))
        for k, p in params.items():
            params[k] = int(p.magnitude) if hasattr(p, "magnitude") else int(p)

        # Temporary fix for engine `int / Quantity` bug (profit_factor)
        import domain.entities.order

        if not hasattr(domain.entities.order.Quantity, "__rtruediv__"):
            domain.entities.order.Quantity.__rtruediv__ = lambda s, o: float(o) / float(s.magnitude)

        try:
            # Build pipeline with current parameters
            pipeline = build_pipeline(
                rsi_period=params.get("rsi_period", RSI_PERIOD_DEFAULT),
                atr_period=params.get("atr_period", ATR_PERIOD_DEFAULT),
                sma_period=params.get("sma_period", SMA_WINDOW_DEFAULT),
                roc_period=params.get("roc_period", 5),
                momentum_period=params.get("momentum_period", 5),
                trend_fast=params.get("trend_fast", 10),
                trend_slow=params.get("trend_slow", 50),
            )

            strategy = StrategyPipeline(strategies=[strategy_class()])
            config = BacktestConfig(initial_capital=initial_capital, warmup_bars=warmup_bars)

            # Grid search stays PURE_SIM — OMS overhead across N combos is real cost.
            engine = BacktestEngine(pipeline, strategy, config, allow_simulate_without_oms=Truemode=ResearchMode.PURE_SIM
            bt_result = engine.run(data, symbol=symbol)

            m = bt_result.metrics
            result_row = {
                "params": params,
                "total_return_pct": m.total_return_pct,
                "sharpe_ratio": m.sharpe_ratio,
                "max_drawdown_pct": m.max_drawdown_pct,
                "total_trades": m.trade_analysis.total_trades,
                "win_rate": m.trade_analysis.win_rate,
                "profit_factor": m.trade_analysis.profit_factor,
            }
            result.results.append(result_row)

            # Track best
            if m.sharpe_ratio > best_sharpe:
                best_sharpe = m.sharpe_ratio
                best_return = m.total_return_pct
                best_params = params

        except Exception as exc:
            logger.warning("Failed for params %s: %s", params, exc)

    result.best_params = best_params
    result.best_return = best_return
    result.best_sharpe = best_sharpe

    # Optional: re-run the winning set once through the real OMS (PARITY).
    if trading_context is not None and best_params:
        logger.info(
            "Re-running best params %s in ResearchMode.PARITY for OMS confirmation",
            best_params,
        )
        pipeline = build_pipeline(
            rsi_period=best_params.get("rsi_period", RSI_PERIOD_DEFAULT),
            atr_period=best_params.get("atr_period", ATR_PERIOD_DEFAULT),
            sma_period=best_params.get("sma_period", SMA_WINDOW_DEFAULT),
            roc_period=best_params.get("roc_period", 5),
            momentum_period=best_params.get("momentum_period", 5),
            trend_fast=best_params.get("trend_fast", 10),
            trend_slow=best_params.get("trend_slow", 50),
        )
        strategy = StrategyPipeline(strategies=[strategy_class()])
        config = BacktestConfig(initial_capital=initial_capital, warmup_bars=warmup_bars)
        parity_engine = BacktestEngine(
            pipeline,
            strategy,
            config,
            mode=ResearchMode.PARITY,
            trading_context=trading_context,
        )
        parity_result = parity_engine.run(data, symbol=symbol)
        result.results.append(
            {
                "params": best_params,
                "parity_confirmation": True,
                "total_return_pct": parity_result.metrics.total_return_pct,
                "sharpe_ratio": parity_result.metrics.sharpe_ratio,
                "max_drawdown_pct": parity_result.metrics.max_drawdown_pct,
                "total_trades": parity_result.metrics.trade_analysis.total_trades,
                "win_rate": parity_result.metrics.trade_analysis.win_rate,
                "profit_factor": parity_result.metrics.trade_analysis.profit_factor,
            }
        )

    return result


def optimize_rsi_period(
    data: pd.DataFrame,
    symbol: str = "OPTIMIZE",
    periods: list[int] | None = None,
    initial_capital: float = 100_000,
) -> OptimizationResult:
    """Quick optimization of RSI period only."""
    if periods is None:
        periods = [5, 7, 10, 14, 21, 28]

    return optimize_grid(
        data=data,
        symbol=symbol,
        param_grids=[ParamGrid("rsi_period", periods)],
        initial_capital=initial_capital,
    )


def optimize_sma_period(
    data: pd.DataFrame,
    symbol: str = "OPTIMIZE",
    periods: list[int] | None = None,
    initial_capital: float = 100_000,
) -> OptimizationResult:
    """Quick optimization of SMA period only."""
    if periods is None:
        periods = [10, 15, 20, 25, 30, 40, 50]

    return optimize_grid(
        data=data,
        symbol=symbol,
        param_grids=[ParamGrid("sma_period", periods)],
        initial_capital=initial_capital,
    )
