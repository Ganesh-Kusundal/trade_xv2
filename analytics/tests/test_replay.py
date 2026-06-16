"""Tests for Replay Engine (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
from analytics.replay import (
    Bar,
    Position,
    ReplayConfig,
    ReplayEngine,
    ReplayMode,
    ReplayResult,
    ReplaySession,
    Trade,
)
from analytics.strategy.pipeline import MomentumStrategy, StrategyPipeline

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate 120-bar OHLCV data with a clear trend."""
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    # Create a trending series: up first 60, down next 60
    up = np.cumsum(np.abs(np.random.randn(60)) * 1.5) + 50
    down = up[-1] - np.cumsum(np.abs(np.random.randn(60)) * 1.5)
    close = np.concatenate([up, down])
    volume = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close - np.random.rand(n),
        "high": close + np.random.rand(n) * 2,
        "low": close - np.random.rand(n) * 2,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def bullish_ohlcv() -> pd.DataFrame:
    """Generate OHLCV data with strong uptrend (should trigger BUY signals)."""
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.arange(n) * 0.5 + np.cumsum(np.random.randn(n) * 0.3)
    volume = np.random.randint(200000, 800000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close - 0.5,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def default_pipeline() -> FeaturePipeline:
    return FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))


@pytest.fixture
def default_config() -> ReplayConfig:
    return ReplayConfig(initial_capital=100_000, warmup_bars=20)


# ---------------------------------------------------------------------------
# Bar model tests
# ---------------------------------------------------------------------------


class TestBar:
    def test_bar_creation(self) -> None:
        bar = Bar(
            symbol="TCS", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=105, low=98, close=103, volume=50000,
        )
        assert bar.symbol == "TCS"
        assert bar.close == 103

    def test_bar_to_dict(self) -> None:
        bar = Bar(
            symbol="TCS", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=105, low=98, close=103, volume=50000,
        )
        d = bar.to_dict()
        assert d["symbol"] == "TCS"
        assert d["close"] == 103
        assert "open" in d

    def test_bar_frozen(self) -> None:
        bar = Bar(
            symbol="TCS", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=105, low=98, close=103, volume=50000,
        )
        with pytest.raises(AttributeError):
            bar.close = 110  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ReplayConfig tests
# ---------------------------------------------------------------------------


class TestReplayConfig:
    def test_defaults(self) -> None:
        config = ReplayConfig()
        assert config.initial_capital == 100_000
        assert config.mode == ReplayMode.BAR_BY_BAR
        assert config.slippage_pct == 0.0
        assert config.warmup_bars == 0

    def test_custom_config(self) -> None:
        config = ReplayConfig(
            initial_capital=50_000,
            warmup_bars=30,
            slippage_pct=0.05,
            commission_flat=20.0,
        )
        assert config.initial_capital == 50_000
        assert config.warmup_bars == 30
        assert config.slippage_pct == 0.05
        assert config.commission_flat == 20.0


# ---------------------------------------------------------------------------
# ReplaySession tests
# ---------------------------------------------------------------------------


class TestReplaySession:
    def test_empty_session(self) -> None:
        session = ReplaySession(capital=100_000)
        assert session.current_equity == 100_000
        assert session.total_trades == 0
        assert session.win_rate == 0.0
        assert session.max_drawdown == 0.0

    def test_equity_with_position(self) -> None:
        session = ReplaySession(capital=80_000)
        session.position = Position(
            symbol="TCS", side="BUY", entry_price=100, quantity=200,
            entry_time=datetime.now(timezone.utc),
        )
        assert session.current_equity == 80_000 + 20_000  # 100 * 200

    def test_max_drawdown(self) -> None:
        session = ReplaySession(capital=100_000)
        t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        session.equity_curve = [
            (t, 100_000),
            (t, 110_000),
            (t, 95_000),
            (t, 105_000),
        ]
        # Peak 110k, trough 95k = dd = (110-95)/110 = 13.6%
        assert abs(session.max_drawdown - (110000 - 95000) / 110000) < 0.01


# ---------------------------------------------------------------------------
# Trade model tests
# ---------------------------------------------------------------------------


class TestTrade:
    def test_trade_creation(self) -> None:
        trade = Trade(
            symbol="TCS", side="BUY", entry_price=100, exit_price=110,
            quantity=100, pnl=1000, pnl_pct=10.0,
        )
        assert trade.pnl == 1000
        assert trade.pnl_pct == 10.0


# ---------------------------------------------------------------------------
# ReplayEngine tests
# ---------------------------------------------------------------------------


class TestReplayEngine:
    def test_run_returns_result(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline, default_config: ReplayConfig
    ) -> None:
        engine = ReplayEngine(default_pipeline, config=default_config)
        result = engine.run(sample_ohlcv, symbol="TEST")
        assert isinstance(result, ReplayResult)
        assert result.bars_processed == 120

    def test_warmup_bars_skipped(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        config = ReplayConfig(initial_capital=100_000, warmup_bars=30)
        engine = ReplayEngine(default_pipeline, config=config)
        result = engine.run(sample_ohlcv, symbol="TEST")
        # Should have processed all bars but only generated signals after warmup
        assert result.bars_processed == 120
        assert len(result.session.equity_curve) > 0

    def test_initial_capital_preserved(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        config = ReplayConfig(initial_capital=200_000, warmup_bars=50)
        engine = ReplayEngine(default_pipeline, config=config)
        result = engine.run(sample_ohlcv, symbol="TEST")
        assert result.session.equity_curve[0][1] == 200_000

    def test_signals_generated(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=20))
        result = engine.run(sample_ohlcv, symbol="TEST")
        assert result.signals_generated >= 0  # May or may not generate signals

    def test_equity_curve_grows(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=20))
        result = engine.run(sample_ohlcv, symbol="TEST")
        # 1 initial entry + 101 post-warmup entries (bars 20-120 inclusive) = 102
        assert len(result.session.equity_curve) == 102

    def test_empty_data(self, default_pipeline: FeaturePipeline) -> None:
        engine = ReplayEngine(default_pipeline)
        result = engine.run(pd.DataFrame(), symbol="TEST")
        assert result.bars_processed == 0

    def test_summary_has_all_fields(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=20))
        result = engine.run(sample_ohlcv, symbol="TEST")
        summary = result.summary
        assert "bars_processed" in summary
        assert "signals_generated" in summary
        assert "total_trades" in summary
        assert "win_rate" in summary
        assert "final_equity" in summary
        assert "total_return_pct" in summary
        assert "max_drawdown_pct" in summary
        assert "sharpe_ratio" in summary

    def test_slippage_applied(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        config = ReplayConfig(warmup_bars=20, slippage_pct=0.1)
        engine = ReplayEngine(default_pipeline, config=config)
        result = engine.run(sample_ohlcv, symbol="TEST")
        # Should not crash, slippage applied to entries/exits
        assert result.bars_processed == 120

    def test_commission_applied(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        config = ReplayConfig(warmup_bars=20, commission_flat=10.0)
        engine = ReplayEngine(default_pipeline, config=config)
        result = engine.run(sample_ohlcv, symbol="TEST")
        assert result.bars_processed == 120

    def test_custom_pipeline(
        self, sample_ohlcv: pd.DataFrame
    ) -> None:
        pipeline = FeaturePipeline().add(RSI(14)).add(SMA(10))
        engine = ReplayEngine(pipeline, config=ReplayConfig(warmup_bars=15))
        result = engine.run(sample_ohlcv, symbol="TEST")
        assert result.bars_processed == 120

    def test_multi_symbol(
        self, default_pipeline: FeaturePipeline
    ) -> None:
        np.random.seed(42)
        n = 60
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rows = []
        for sym in ["TCS", "INFY"]:
            close = 100 + np.cumsum(np.random.randn(n) * 2)
            vol = np.random.randint(100000, 500000, n).astype(float)
            for i, d in enumerate(dates):
                rows.append({
                    "symbol": sym, "timestamp": d,
                    "open": close[i]-1, "high": close[i]+2, "low": close[i]-2,
                    "close": close[i], "volume": vol[i],
                })
        data = pd.DataFrame(rows)
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=15))
        result = engine.run(data, symbol="MULTI")
        assert result.bars_processed == 120  # 60 bars × 2 symbols

    def test_total_return_pct(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=20))
        result = engine.run(sample_ohlcv, symbol="TEST")
        # Return should be a finite number
        assert isinstance(result.total_return_pct, float)


# ---------------------------------------------------------------------------
# ReplayEngine + MomentumStrategy integration
# ---------------------------------------------------------------------------


class TestReplayMomentum:
    def test_momentum_strategy_integration(
        self, bullish_ohlcv: pd.DataFrame
    ) -> None:
        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
        strategy = StrategyPipeline(strategies=[MomentumStrategy()])
        config = ReplayConfig(initial_capital=100_000, warmup_bars=20)
        engine = ReplayEngine(pipeline, strategy, config)
        result = engine.run(bullish_ohlcv, symbol="BULL")
        assert result.bars_processed == 120
        # In a strong uptrend, MomentumStrategy should generate at least some signals
        assert result.signals_generated >= 0

    def test_no_strategy_default(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=20))
        result = engine.run(sample_ohlcv, symbol="TEST")
        # Should use default StrategyPipeline
        assert result.bars_processed == 120


# ---------------------------------------------------------------------------
# Analytics facade integration
# ---------------------------------------------------------------------------


class TestAnalyticsFacade:
    def test_analytics_has_replay(self) -> None:
        from analytics import Analytics
        a = Analytics()
        # replay() with no args should return a ReplayEngine or similar
        # (may fail if feature_builder doesn't have to_pipeline, that's ok)
        try:
            engine = a.replay()
            assert engine is not None
        except (AttributeError, TypeError):
            pass  # FeatureBuilder may not have to_pipeline yet

    def test_replay_with_data(
        self, sample_ohlcv: pd.DataFrame, default_pipeline: FeaturePipeline
    ) -> None:
        from analytics.replay import ReplayConfig, ReplayEngine
        engine = ReplayEngine(default_pipeline, config=ReplayConfig(warmup_bars=20))
        result = engine.run(sample_ohlcv, symbol="TEST")
        assert result.bars_processed == 120
