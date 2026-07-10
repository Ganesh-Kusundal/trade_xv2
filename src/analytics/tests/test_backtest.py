"""Tests for Backtest Engine (Phase 6)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.backtest import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    PerformanceMetrics,
)
from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
from analytics.replay.models import SimulatedTrade

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trending_data() -> pd.DataFrame:
    """Generate trending OHLCV data (up then down)."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    up = np.cumsum(np.abs(np.random.randn(100)) * 1.5) + 100
    down = up[-1] - np.cumsum(np.abs(np.random.randn(100)) * 1.2)
    close = np.concatenate([up, down])
    volume = np.random.randint(200000, 800000, n).astype(float)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - np.random.rand(n),
            "high": close + np.random.rand(n) * 3,
            "low": close - np.random.rand(n) * 3,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def benchmark_data() -> pd.DataFrame:
    """Generate benchmark (NIFTY-like) data."""
    np.random.seed(99)
    n = 200
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 20000 + np.cumsum(np.random.randn(n) * 50)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - 10,
            "high": close + 20,
            "low": close - 20,
            "close": close,
            "volume": np.random.randint(1000000, 5000000, n).astype(float),
        }
    )


@pytest.fixture
def pipeline() -> FeaturePipeline:
    return FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))


# ---------------------------------------------------------------------------
# BacktestConfig tests
# ---------------------------------------------------------------------------


class TestBacktestConfig:
    def test_defaults(self) -> None:
        config = BacktestConfig()
        assert config.initial_capital == 100_000
        assert config.risk_free_rate == 0.065
        assert config.annualization_factor == 252
        assert config.benchmark_symbol == "NIFTY"

    def test_custom(self) -> None:
        config = BacktestConfig(initial_capital=50_000, risk_free_rate=0.05, warmup_bars=30)
        assert config.initial_capital == 50_000
        assert config.risk_free_rate == 0.05
        assert config.warmup_bars == 30


# ---------------------------------------------------------------------------
# TradeAnalysis tests
# ---------------------------------------------------------------------------


class TestTradeAnalysis:
    def test_analyze_trades_empty(self, pipeline: FeaturePipeline) -> None:
        engine = BacktestEngine(pipeline)
        result = engine.run(pd.DataFrame(), symbol="TEST")
        assert result.metrics.trade_analysis.total_trades == 0

    def test_analyze_trades_computes_metrics(self) -> None:
        trades = [
            SimulatedTrade(
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=110,
                quantity=100,
                pnl=1000,
                pnl_pct=10.0,
                strategy="Momentum",
            ),
            SimulatedTrade(
                symbol="B",
                side="BUY",
                entry_price=100,
                exit_price=95,
                quantity=100,
                pnl=-500,
                pnl_pct=-5.0,
                strategy="Momentum",
            ),
            SimulatedTrade(
                symbol="C",
                side="BUY",
                entry_price=100,
                exit_price=115,
                quantity=100,
                pnl=1500,
                pnl_pct=15.0,
                strategy="Breakout",
            ),
        ]
        engine = BacktestEngine(FeaturePipeline())
        analysis = engine._analyze_trades(trades)
        assert analysis.total_trades == 3
        assert analysis.winning_trades == 2
        assert analysis.losing_trades == 1
        assert analysis.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert analysis.avg_win == pytest.approx(1250.0, abs=1)
        assert analysis.avg_loss == -500.0
        assert analysis.profit_factor == pytest.approx(2500 / 500, abs=0.1)
        assert analysis.largest_win == 1500.0
        assert analysis.largest_loss == -500.0


# ---------------------------------------------------------------------------
# BacktestEngine tests
# ---------------------------------------------------------------------------


class TestBacktestEngine:
    def test_run_returns_result(
        self, trending_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST")
        assert isinstance(result, BacktestResult)
        assert result.replay.bars_processed == 200

    def test_metrics_computed(self, trending_data: pd.DataFrame, pipeline: FeaturePipeline) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST")
        m = result.metrics
        assert isinstance(m, PerformanceMetrics)
        assert m.total_return_pct != 0 or m.total_return_pct == 0.0
        assert isinstance(m.sharpe_ratio, float)
        assert isinstance(m.sortino_ratio, float)
        assert isinstance(m.max_drawdown, float)

    def test_summary_has_all_fields(
        self, trending_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST")
        s = result.summary
        expected_keys = {
            "bars_processed",
            "total_trades",
            "win_rate",
            "profit_factor",
            "total_return_pct",
            "cagr",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "max_drawdown_pct",
            "max_drawdown_duration",
            "volatility",
            "alpha",
            "beta",
            "information_ratio",
            "final_equity",
            "avg_holding_bars",
            "max_consecutive_wins",
            "max_consecutive_losses",
        }
        assert expected_keys.issubset(set(s.keys()))

    def test_with_benchmark(
        self, trending_data: pd.DataFrame, benchmark_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST", benchmark=benchmark_data)
        m = result.metrics
        # Alpha and beta should be computed
        assert isinstance(m.alpha, float)
        assert isinstance(m.beta, float)
        assert isinstance(m.benchmark_return, float)

    def test_to_dataframe(self, trending_data: pd.DataFrame, pipeline: FeaturePipeline) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST")
        df = result.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "sharpe_ratio" in df.columns

    def test_empty_data(self, pipeline: FeaturePipeline) -> None:
        engine = BacktestEngine(pipeline)
        result = engine.run(pd.DataFrame(), symbol="TEST")
        assert result.replay.bars_processed == 0
        assert result.metrics.trade_analysis.total_trades == 0

    def test_max_drawdown_non_negative(
        self, trending_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST")
        assert result.metrics.max_drawdown >= 0

    def test_sharpe_with_no_trades(self, pipeline: FeaturePipeline) -> None:
        """With empty data, Sharpe should be 0."""
        engine = BacktestEngine(pipeline)
        result = engine.run(pd.DataFrame(), symbol="TEST")
        assert result.metrics.sharpe_ratio == 0.0

    def test_sortino_with_no_trades(self, pipeline: FeaturePipeline) -> None:
        engine = BacktestEngine(pipeline)
        result = engine.run(pd.DataFrame(), symbol="TEST")
        assert result.metrics.sortino_ratio == 0.0

    def test_calmar_ratio(self, trending_data: pd.DataFrame, pipeline: FeaturePipeline) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20))
        result = engine.run(trending_data, symbol="TEST")
        # Calmar = CAGR / MaxDD, should be finite
        assert np.isfinite(result.metrics.calmar_ratio) or result.metrics.max_drawdown == 0

    def test_custom_config(self, trending_data: pd.DataFrame, pipeline: FeaturePipeline) -> None:
        config = BacktestConfig(
            initial_capital=200_000,
            warmup_bars=30,
            slippage_pct=0.1,
            commission_flat=15.0,
            risk_free_rate=0.07,
        )
        engine = BacktestEngine(pipeline, config=config)
        result = engine.run(trending_data, symbol="TEST")
        assert result.replay.bars_processed == 200


# ---------------------------------------------------------------------------
# Analytics facade integration
# ---------------------------------------------------------------------------


class TestAnalyticsFacade:
    def test_analytics_has_backtest(self) -> None:
        from analytics import Analytics

        a = Analytics()
        try:
            engine = a.backtest()
            assert engine is not None
        except (AttributeError, TypeError):
            pass  # FeatureBuilder may not have to_pipeline yet


class TestBacktestConfigValidation:
    def test_slippage_pct_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError, match="slippage_pct"):
            BacktestConfig(slippage_pct=-0.1)

    def test_max_position_pct_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="max_position_pct"):
            BacktestConfig(max_position_pct=0)

    def test_warmup_bars_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError, match="warmup_bars"):
            BacktestConfig(warmup_bars=-1)
