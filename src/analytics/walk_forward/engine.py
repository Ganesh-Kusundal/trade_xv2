"""Walk-forward testing — rolling train/test windows for strategy validation."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
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

    def run(self, df: pd.DataFrame, symbol: str = "TEST", max_workers: int | None = None) -> WalkForwardResult:
        """Execute walk-forward windows over *df*.

        Parameters
        ----------
        df:
            OHLCV DataFrame.
        symbol:
            Symbol name for the backtest.
        max_workers:
            Number of parallel workers. Defaults to min(cpu_count, window_count).
            Set to 1 to force sequential execution (useful for debugging).
        """
        cfg = self._config

        # Pre-compute all window boundaries
        windows: list[tuple[int, int, int, int]] = []  # (start, train_end, test_end, window_idx)
        start = 0
        window_idx = 0
        while start + cfg.train_bars + cfg.test_bars <= len(df):
            train_end = start + cfg.train_bars
            test_end = train_end + cfg.test_bars
            windows.append((start, train_end, test_end, window_idx))
            window_idx += 1
            start += cfg.step_bars

        if not windows:
            result = WalkForwardResult()
            logger.info("Walk-forward complete: 0 windows (insufficient data)")
            return result

        # Choose execution mode: sequential by default (safe for all pipelines),
        # parallel only when explicitly requested via max_workers > 1.
        # Sequential default avoids PicklingError with unpicklable pipeline objects.
        effective_workers = max_workers if max_workers is not None else 1

        if effective_workers <= 1 or len(windows) <= 1:
            window_results = [
                self._run_window(df, symbol, s, te, tend, wi)
                for s, te, tend, wi in windows
            ]
        else:
            window_results = self._run_windows_parallel(
                df, symbol, windows, effective_workers
            )

        # Aggregate results
        result = WalkForwardResult()
        sharpe_values: list[float] = []
        for wr in window_results:
            result.windows.append(wr)
            result.total_pnl += wr["pnl"]
            sharpe_values.append(wr["sharpe"])

        if sharpe_values:
            result.avg_sharpe = sum(sharpe_values) / len(sharpe_values)

        logger.info(
            "Walk-forward complete: %d windows, total_pnl=%.2f",
            result.window_count,
            result.total_pnl,
        )
        return result

    def _run_window(
        self,
        df: pd.DataFrame,
        symbol: str,
        start: int,
        train_end: int,
        test_end: int,
        window_idx: int,
    ) -> dict[str, Any]:
        """Run a single walk-forward window."""
        cfg = self._config
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
        return {
            "window": window_idx,
            "train_start": start,
            "test_start": train_end,
            "test_end": test_end,
            "pnl": pnl,
            "sharpe": sharpe,
        }

    def _run_windows_parallel(
        self,
        df: pd.DataFrame,
        symbol: str,
        windows: list[tuple[int, int, int, int]],
        max_workers: int,
    ) -> list[dict[str, Any]]:
        """Run walk-forward windows in parallel using ProcessPoolExecutor."""
        results: list[dict[str, Any]] = [None] * len(windows)  # type: ignore[list-item]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _run_window_standalone,
                    self._pipeline,
                    self._strategy_pipeline,
                    self._config,
                    df,
                    symbol,
                    s,
                    te,
                    tend,
                    wi,
                ): i
                for i, (s, te, tend, wi) in enumerate(windows)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error("Walk-forward window %d failed: %s", idx, exc)
                    results[idx] = {
                        "window": windows[idx][3],
                        "train_start": windows[idx][0],
                        "test_start": windows[idx][1],
                        "test_end": windows[idx][2],
                        "pnl": 0.0,
                        "sharpe": 0.0,
                    }

        return results


def _run_window_standalone(
    pipeline: FeaturePipeline,
    strategy_pipeline: StrategyPipeline,
    config: WalkForwardConfig,
    df: pd.DataFrame,
    symbol: str,
    start: int,
    train_end: int,
    test_end: int,
    window_idx: int,
) -> dict[str, Any]:
    """Module-level function for parallel execution (picklable)."""
    test_slice = df.iloc[train_end:test_end].copy()
    bt_config = BacktestConfig(initial_capital=config.initial_capital)
    engine = BacktestEngine(pipeline, strategy_pipeline, bt_config)
    bt_result = engine.run(test_slice, symbol=symbol)

    metrics = getattr(bt_result, "metrics", None)
    ta = getattr(metrics, "trade_analysis", None) if metrics else None
    pnl = float(getattr(ta, "total_pnl", 0.0) if ta else 0.0)
    sharpe = float(getattr(metrics, "sharpe_ratio", 0.0) if metrics else 0.0)
    return {
        "window": window_idx,
        "train_start": start,
        "test_start": train_end,
        "test_end": test_end,
        "pnl": pnl,
        "sharpe": sharpe,
    }
