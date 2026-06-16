"""Tests for strategy parameter optimization."""

from __future__ import annotations

import pandas as pd

from analytics.backtest.optimizer import (
    OptimizationResult,
    ParamGrid,
    build_pipeline,
    optimize_grid,
    optimize_rsi_period,
    optimize_sma_period,
)


def _ohlcv(n: int = 100) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    import numpy as np

    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": close - 0.5,
        "high": close + 1.5,
        "low": close - 1.5,
        "close": close,
        "volume": [1000 + (i % 5) * 100 for i in range(n)],
    })


class TestParamGrid:
    def test_creation(self) -> None:
        grid = ParamGrid(name="rsi_period", values=[7, 14, 21])
        assert grid.name == "rsi_period"
        assert grid.values == [7, 14, 21]

    def test_values_types(self) -> None:
        grid = ParamGrid(name="multiplier", values=[1.0, 1.5, 2.0])
        assert all(isinstance(v, float) for v in grid.values)


class TestOptimizationResult:
    def test_empty(self) -> None:
        result = OptimizationResult(param_name="test", param_values=[])
        assert result.results == []
        assert result.best_params == {}
        assert result.best_return == 0.0
        assert result.best_sharpe == 0.0

    def test_summary_property(self) -> None:
        result = OptimizationResult(
            param_name="rsi",
            param_values=["7", "14"],
            results=[{"params": {"rsi": 7}, "total_return_pct": 5.0}],
        )
        df = result.summary
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


class TestBuildPipeline:
    def test_default(self) -> None:
        pipeline = build_pipeline()
        assert pipeline is not None

    def test_custom_params(self) -> None:
        pipeline = build_pipeline(rsi_period=21, sma_period=50)
        assert pipeline is not None


class TestOptimizeGrid:
    def test_single_param(self) -> None:
        data = _ohlcv(100)
        result = optimize_grid(
            data=data,
            symbol="TEST",
            param_grids=[ParamGrid("rsi_period", [7, 14])],
            initial_capital=100_000,
            warmup_bars=30,
        )
        assert isinstance(result, OptimizationResult)
        assert len(result.results) == 2
        assert result.best_params != {}

    def test_two_params(self) -> None:
        data = _ohlcv(100)
        result = optimize_grid(
            data=data,
            symbol="TEST",
            param_grids=[
                ParamGrid("rsi_period", [7, 14]),
                ParamGrid("sma_period", [10, 20]),
            ],
            initial_capital=100_000,
            warmup_bars=30,
        )
        assert len(result.results) == 4

    def test_best_params_found(self) -> None:
        data = _ohlcv(100)
        result = optimize_grid(
            data=data,
            symbol="TEST",
            param_grids=[ParamGrid("rsi_period", [7, 14, 21])],
            initial_capital=100_000,
            warmup_bars=30,
        )
        assert "rsi_period" in result.best_params
        assert result.best_params["rsi_period"] in [7, 14, 21]

    def test_summary_dataframe(self) -> None:
        data = _ohlcv(100)
        result = optimize_grid(
            data=data,
            symbol="TEST",
            param_grids=[ParamGrid("rsi_period", [7, 14])],
            initial_capital=100_000,
            warmup_bars=30,
        )
        df = result.summary
        assert "params" in df.columns
        assert "total_return_pct" in df.columns

    def test_breakout_strategy(self) -> None:
        data = _ohlcv(100)
        result = optimize_grid(
            data=data,
            symbol="TEST",
            param_grids=[ParamGrid("rsi_period", [7, 14])],
            strategy_name="breakout",
            initial_capital=100_000,
            warmup_bars=30,
        )
        assert len(result.results) == 2


class TestOptimizeRsiPeriod:
    def test_default_periods(self) -> None:
        data = _ohlcv(100)
        result = optimize_rsi_period(data=data, symbol="TEST")
        assert len(result.results) == 6  # default 6 periods

    def test_custom_periods(self) -> None:
        data = _ohlcv(100)
        result = optimize_rsi_period(data=data, symbol="TEST", periods=[7, 14])
        assert len(result.results) == 2


class TestOptimizeSmaPeriod:
    def test_default_periods(self) -> None:
        data = _ohlcv(100)
        result = optimize_sma_period(data=data, symbol="TEST")
        assert len(result.results) == 7  # default 7 periods

    def test_custom_periods(self) -> None:
        data = _ohlcv(100)
        result = optimize_sma_period(data=data, symbol="TEST", periods=[10, 20])
        assert len(result.results) == 2
