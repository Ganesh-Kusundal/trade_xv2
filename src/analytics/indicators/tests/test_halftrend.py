"""Tests for HalfTrend indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.indicators.halftrend import HalfTrend


def _make_ohlcv(n: int = 200, start_price: float = 100.0, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="1min")

    if trend == "up":
        close = start_price + np.cumsum(np.random.randn(n) * 0.5 + 0.1)
    elif trend == "down":
        close = start_price + np.cumsum(np.random.randn(n) * 0.5 - 0.1)
    else:
        close = start_price + np.cumsum(np.random.randn(n) * 0.5)

    close = np.maximum(close, 1.0)  # Prevent negative prices
    high = close + np.abs(np.random.randn(n) * 0.5)
    low = close - np.abs(np.random.randn(n) * 0.5)
    open_ = close + np.random.randn(n) * 0.3
    volume = np.random.randint(1000, 100000, n)

    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "oi": 0,
            "symbol": "TEST",
            "exchange": "NSE",
            "timeframe": "1m",
        }
    )


class TestHalfTrend:
    """Test HalfTrend indicator."""

    def test_basic_computation(self):
        """HalfTrend adds expected columns to DataFrame."""
        df = _make_ohlcv(200)
        ht = HalfTrend(period=10, atr_period=10, deviation=1.0)
        result = ht.compute(df)

        assert "halftrend" in result.columns
        assert "halftrend_direction" in result.columns
        assert "halftrend_signal" in result.columns
        assert len(result) == len(df)

    def test_empty_dataframe(self):
        """HalfTrend handles empty DataFrame gracefully."""
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        ht = HalfTrend()
        result = ht.compute(df)

        assert result.empty
        assert "halftrend" in result.columns
        assert "halftrend_direction" in result.columns
        assert "halftrend_signal" in result.columns

    def test_insufficient_data(self):
        """HalfTrend handles insufficient data gracefully."""
        df = _make_ohlcv(5)  # Less than period + atr_period
        ht = HalfTrend(period=10, atr_period=10)
        result = ht.compute(df)

        assert len(result) == 5
        assert result["halftrend_direction"].sum() == 0  # All zeros

    def test_direction_values(self):
        """HalfTrend direction is 1 (up), -1 (down), or 0 (undefined)."""
        df = _make_ohlcv(300)
        ht = HalfTrend(period=10, atr_period=10, deviation=1.0)
        result = ht.compute(df)

        valid_directions = {-1, 0, 1}
        assert all(d in valid_directions for d in result["halftrend_direction"].unique())

    def test_signal_values(self):
        """HalfTrend signal is BUY, SELL, or HOLD."""
        df = _make_ohlcv(300)
        ht = HalfTrend(period=10, atr_period=10, deviation=1.0)
        result = ht.compute(df)

        valid_signals = {"BUY", "SELL", "HOLD"}
        assert all(s in valid_signals for s in result["halftrend_signal"].unique())

    def test_cooldown_reduces_signals(self):
        """Cooldown parameter reduces number of signals."""
        df = _make_ohlcv(500)

        ht_no_cooldown = HalfTrend(period=10, atr_period=10, deviation=1.0, cooldown=0)
        result_no_cooldown = ht_no_cooldown.compute(df)
        signals_no_cooldown = (result_no_cooldown["halftrend_signal"] != "HOLD").sum()

        ht_with_cooldown = HalfTrend(period=10, atr_period=10, deviation=1.0, cooldown=100)
        result_with_cooldown = ht_with_cooldown.compute(df)
        signals_with_cooldown = (result_with_cooldown["halftrend_signal"] != "HOLD").sum()

        assert signals_with_cooldown <= signals_no_cooldown

    def test_cooldown_enforced(self):
        """Cooldown ensures minimum bars between signals."""
        df = _make_ohlcv(500)
        cooldown = 50
        ht = HalfTrend(period=10, atr_period=10, deviation=1.0, cooldown=cooldown)
        result = ht.compute(df)

        signal_indices = result[result["halftrend_signal"] != "HOLD"].index.tolist()
        for i in range(1, len(signal_indices)):
            gap = signal_indices[i] - signal_indices[i - 1]
            assert gap >= cooldown, (
                f"Gap between signals {i - 1} and {i} is {gap}, expected >= {cooldown}"
            )

    def test_uptrend_follows_price(self):
        """In uptrend, HalfTrend line follows price upward."""
        df = _make_ohlcv(300, trend="up")
        ht = HalfTrend(period=10, atr_period=10, deviation=1.0)
        result = ht.compute(df)

        # In uptrend, HT line should generally be below close
        valid = result.dropna(subset=["halftrend"])
        if len(valid) > 50:
            uptrend_mask = valid["halftrend_direction"] == 1
            if uptrend_mask.sum() > 10:
                uptrend_data = valid[uptrend_mask]
                # HT line should be below close in uptrend (it acts as support)
                below_close = (uptrend_data["halftrend"] < uptrend_data["close"]).mean()
                assert below_close > 0.5, (
                    f"Expected HT below close in uptrend, got {below_close:.2%}"
                )

    def test_downtrend_follows_price(self):
        """In downtrend, HalfTrend line follows price downward."""
        df = _make_ohlcv(300, trend="down")
        ht = HalfTrend(period=10, atr_period=10, deviation=1.0)
        result = ht.compute(df)

        valid = result.dropna(subset=["halftrend"])
        if len(valid) > 50:
            downtrend_mask = valid["halftrend_direction"] == -1
            if downtrend_mask.sum() > 10:
                downtrend_data = valid[downtrend_mask]
                # HT line should be above close in downtrend (it acts as resistance)
                above_close = (downtrend_data["halftrend"] > downtrend_data["close"]).mean()
                assert above_close > 0.5, (
                    f"Expected HT above close in downtrend, got {above_close:.2%}"
                )

    def test_halftrend_not_nan_after_warmup(self):
        """HalfTrend values are not NaN after warmup period."""
        df = _make_ohlcv(200)
        ht = HalfTrend(period=10, atr_period=10)
        result = ht.compute(df)

        # After warmup, halftrend should have values
        warmup = max(ht.period, ht.atr_period)
        after_warmup = result.iloc[warmup:]
        assert after_warmup["halftrend"].notna().all()

    def test_pipeline_compatibility(self):
        """HalfTrend works with FeaturePipeline."""
        from analytics.pipeline.pipeline import FeaturePipeline

        df = _make_ohlcv(200)
        pipeline = FeaturePipeline()
        pipeline.add(HalfTrend(period=10, atr_period=10, deviation=1.0))

        result = pipeline.run(df)
        assert "halftrend" in result.columns
        assert "halftrend_direction" in result.columns
        assert "halftrend_signal" in result.columns

    def test_name_attribute(self):
        """HalfTrend has correct name attribute."""
        ht = HalfTrend()
        assert ht.name == "halftrend"

        ht_custom = HalfTrend(name="my_halftrend")
        assert ht_custom.name == "my_halftrend"

    def test_different_parameters(self):
        """HalfTrend works with different parameter combinations."""
        df = _make_ohlcv(300)

        for period, atr_period, deviation in [(5, 5, 0.5), (20, 20, 2.0), (10, 15, 1.5)]:
            ht = HalfTrend(period=period, atr_period=atr_period, deviation=deviation)
            result = ht.compute(df)
            assert "halftrend" in result.columns
            assert len(result) == len(df)
