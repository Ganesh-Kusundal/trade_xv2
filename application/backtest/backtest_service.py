"""Backtest service for executing backtest runs.

Extracts backtest orchestration logic from API route handlers into
testable services.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestMetrics:
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


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    symbol: str
    timeframe: str
    metrics: BacktestMetrics


class BacktestService:
    """Service for executing backtest runs.

    Encapsulates backtest pipeline construction, strategy selection,
    and result mapping that was previously in API route handlers.
    """

    def __init__(self, datalake_gateway: Any) -> None:
        self._gateway = datalake_gateway

    def run_backtest(
        self,
        symbol: str,
        strategy: str = "momentum",
        timeframe: str = "1d",
        years: int = 1,
        initial_capital: float = 100_000.0,
    ) -> BacktestResult:
        """Execute a backtest.

        Parameters
        ----------
        symbol : str
            Symbol to backtest.
        strategy : str
            Strategy name (momentum, breakout).
        timeframe : str
            Bar timeframe (1m, 5m, 15m, 1h, 1d).
        years : int
            Years of historical data.
        initial_capital : float
            Starting capital.

        Returns
        -------
        BacktestResult
            Backtest results with metrics.
        """
        import pandas as pd

        from analytics.backtest import BacktestConfig, BacktestEngine
        from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
        from analytics.strategy import BreakoutStrategy, MomentumStrategy, StrategyPipeline

        lookback_days = years * 365
        df = self._gateway.history(
            symbol=symbol,
            exchange="NSE",
            timeframe=timeframe,
            lookback_days=lookback_days,
        )

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise ValueError(f"No historical data for symbol '{symbol}'")

        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))

        strategy_map = {
            "momentum": MomentumStrategy,
            "breakout": BreakoutStrategy,
        }
        strategy_cls = strategy_map.get(strategy, MomentumStrategy)
        strategy_pipeline = StrategyPipeline(strategies=[strategy_cls()])

        config = BacktestConfig(
            initial_capital=initial_capital,
            warmup_bars=20,
        )
        engine = BacktestEngine(pipeline, strategy_pipeline, config)
        result = engine.run(df, symbol=symbol)

        m = result.metrics
        run_id = str(uuid.uuid4())[:12]

        return BacktestResult(
            run_id=run_id,
            symbol=symbol,
            timeframe=timeframe,
            metrics=BacktestMetrics(
                total_return_pct=round(m.total_return_pct, 2),
                annualized_return_pct=round(m.cagr, 2),
                sharpe_ratio=round(m.sharpe_ratio, 2),
                sortino_ratio=round(m.sortino_ratio, 2),
                max_drawdown_pct=round(m.max_drawdown, 2),
                profit_factor=round(m.trade_analysis.profit_factor, 2),
                win_rate=round(m.trade_analysis.win_rate, 2),
                total_trades=m.trade_analysis.total_trades,
                winning_trades=m.trade_analysis.winning_trades,
                losing_trades=m.trade_analysis.losing_trades,
            ),
        )
