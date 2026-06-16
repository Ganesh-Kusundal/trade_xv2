"""Tests for backtest comparison."""

from __future__ import annotations

import pandas as pd

from analytics.backtest.comparator import (
    ComparisonResult,
    compare_parameters,
    compare_strategies,
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


class TestComparisonResult:
    def test_empty(self) -> None:
        result = ComparisonResult()
        assert result.results == []
        assert result.best is None
        assert result.summary.empty

    def test_with_results(self) -> None:
        result = ComparisonResult(results=[
            {"strategy": "momentum", "sharpe_ratio": 1.5, "total_return_pct": 10.0},
            {"strategy": "breakout", "sharpe_ratio": 0.8, "total_return_pct": 5.0},
        ])
        assert len(result.results) == 2
        assert result.best["strategy"] == "momentum"

    def test_summary_dataframe(self) -> None:
        result = ComparisonResult(results=[
            {"strategy": "momentum", "sharpe_ratio": 1.5},
        ])
        df = result.summary
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


class TestCompareStrategies:
    def test_default_strategies(self) -> None:
        data = _ohlcv(100)
        result = compare_strategies(data=data, symbol="TEST")
        assert isinstance(result, ComparisonResult)
        assert len(result.results) == 2
        assert result.best is not None

    def test_momentum_only(self) -> None:
        data = _ohlcv(100)
        result = compare_strategies(data=data, symbol="TEST", strategies=["momentum"])
        assert len(result.results) == 1
        assert result.results[0]["strategy"] == "momentum"

    def test_breakout_only(self) -> None:
        data = _ohlcv(100)
        result = compare_strategies(data=data, symbol="TEST", strategies=["breakout"])
        assert len(result.results) == 1
        assert result.results[0]["strategy"] == "breakout"

    def test_result_fields(self) -> None:
        data = _ohlcv(100)
        result = compare_strategies(data=data, symbol="TEST", strategies=["momentum"])
        row = result.results[0]
        assert "total_return_pct" in row
        assert "sharpe_ratio" in row
        assert "max_drawdown_pct" in row
        assert "total_trades" in row
        assert "win_rate" in row
        assert "profit_factor" in row


class TestCompareParameters:
    def test_default_params(self) -> None:
        data = _ohlcv(100)
        result = compare_parameters(data=data, symbol="TEST")
        assert len(result.results) == 3  # default 3 param sets

    def test_custom_params(self) -> None:
        data = _ohlcv(100)
        param_sets = [
            {"rsi_period": 7, "sma_period": 10},
            {"rsi_period": 14, "sma_period": 20},
        ]
        result = compare_parameters(data=data, symbol="TEST", param_sets=param_sets)
        assert len(result.results) == 2

    def test_best_by_sharpe(self) -> None:
        data = _ohlcv(100)
        result = compare_parameters(data=data, symbol="TEST")
        assert result.best is not None
        assert "sharpe_ratio" in result.best

    def test_result_fields(self) -> None:
        data = _ohlcv(100)
        result = compare_parameters(data=data, symbol="TEST", param_sets=[{"rsi_period": 14}])
        row = result.results[0]
        assert "params" in row
        assert "total_return_pct" in row
        assert "sharpe_ratio" in row
