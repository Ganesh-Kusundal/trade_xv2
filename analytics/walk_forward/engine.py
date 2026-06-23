"""Walk-forward testing — rolling train/test windows for strategy validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from analytics.backtest.engine import BacktestEngine
from analytics.backtest.models import BacktestConfig
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.strategy.pipeline import StrategyPipeline

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward analysis."""

    train_bars: int = 500
    test_bars: int = 100
    step_bars: int = 100
    initial_capital: float = 100_000.0


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward results."""

    windows: list[dict[str, Any]] = field(default_factory=list)
    total_pnl: float = 0.0
    avg_sharpe: float = 0.0

    @property
    def window_count(self) -> int:
        return len(self.windows)


class WalkForwardEngine:
    """Run rolling train/test backtests across a single OHLCV series."""

    def __init__(
        self,
        pipeline: FeaturePipeline,
        strategy_pipeline: StrategyPipeline,
        config: WalkForwardConfig | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._strategy_pipeline = strategy_pipeline
        self._config = config or WalkForwardConfig()

    def run(self, df: pd.DataFrame, symbol: str = "TEST") -> WalkForwardResult:
        """Execute walk-forward windows over *df*."""
        cfg = self._config
        result = WalkForwardResult()
        sharpe_values: list[float] = []

        start = 0
        window_idx = 0
        while start + cfg.train_bars + cfg.test_bars <= len(df):
            train_end = start + cfg.train_bars
            test_end = train_end + cfg.test_bars
            test_slice = df.iloc[train_end:test_end].copy()

            bt_config = BacktestConfig(initial_capital=cfg.initial_capital)
            engine = BacktestEngine(
                self._pipeline,
                self._strategy_pipeline,
                bt_config,
            )
            bt_result = engine.run(test_slice, symbol=symbol)

            metrics = getattr(bt_result, "metrics", None)
            ta = getattr(metrics, "trade_analysis", None) if metrics else None
            pnl = float(getattr(ta, "total_pnl", 0.0) if ta else 0.0)
            sharpe = float(getattr(metrics, "sharpe_ratio", 0.0) if metrics else 0.0)
            result.windows.append({
                "window": window_idx,
                "train_start": start,
                "test_start": train_end,
                "test_end": test_end,
                "pnl": pnl,
                "sharpe": sharpe,
            })
            result.total_pnl += pnl
            sharpe_values.append(sharpe)
            window_idx += 1
            start += cfg.step_bars

        if sharpe_values:
            result.avg_sharpe = sum(sharpe_values) / len(sharpe_values)

        logger.info(
            "Walk-forward complete: %d windows, total_pnl=%.2f",
            result.window_count,
            result.total_pnl,
        )
        return result
