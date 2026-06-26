"""Tests for datalake.features — quantitative feature engineering."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from datalake.features import (
    rsi, macd, roc, adx, cci, williams_r, stochastic,
    bollinger_bands, zscore, atr, historical_volatility,
    garman_klass_vol, parkinson_vol, yang_zhang_vol,
    obv, vwap_deviation, compute_all_features,
)


@pytest.fixture
def sample_ohlcv():
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2024-01-01", periods=n, freq="1D")
    close = 1000 + np.cumsum(np.random.randn(n) * 10)
    return pd.DataFrame({
        "timestamp": dates,
        "open": close - 2,
        "high": close + 5,
        "low": close - 5,
        "close": close,
        "volume": np.random.randint(10000, 100000, n),
    })


class TestMomentum:
    def test_rsi_range(self, sample_ohlcv):
        result = rsi(sample_ohlcv["close"], 14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_macd_columns(self, sample_ohlcv):
        result = macd(sample_ohlcv["close"])
        assert list(result.columns) == ["macd", "macd_signal", "macd_histogram"]
        assert len(result) == len(sample_ohlcv)

    def test_roc(self, sample_ohlcv):
        result = roc(sample_ohlcv["close"], 10)
        assert result.iloc[10] == pytest.approx(
            (sample_ohlcv["close"].iloc[10] / sample_ohlcv["close"].iloc[0] - 1) * 100,
            abs=0.01,
        )

    def test_adx_columns(self, sample_ohlcv):
        result = adx(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert list(result.columns) == ["adx", "plus_di", "minus_di"]

    def test_williams_r_range(self, sample_ohlcv):
        result = williams_r(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        valid = result.dropna()
        assert (valid >= -100).all()
        assert (valid <= 0).all()

    def test_stochastic_columns(self, sample_ohlcv):
        result = stochastic(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert list(result.columns) == ["stoch_k", "stoch_d"]


class TestMeanReversion:
    def test_bollinger_columns(self, sample_ohlcv):
        result = bollinger_bands(sample_ohlcv["close"])
        assert list(result.columns) == ["bb_upper", "bb_mid", "bb_lower", "bb_bandwidth", "bb_pct_b"]

    def test_bollinger_bandwidth_positive(self, sample_ohlcv):
        result = bollinger_bands(sample_ohlcv["close"])
        valid = result["bb_bandwidth"].dropna()
        assert (valid >= 0).all()

    def test_zscore(self, sample_ohlcv):
        result = zscore(sample_ohlcv["close"], 20)
        valid = result.dropna()
        assert abs(valid.mean()) < 1.0


class TestVolatility:
    def test_atr_positive(self, sample_ohlcv):
        result = atr(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        valid = result.dropna()
        assert (valid > 0).all()

    def test_historical_vol(self, sample_ohlcv):
        result = historical_volatility(sample_ohlcv["close"], 20)
        valid = result.dropna()
        assert (valid > 0).all()
        assert (valid < 5.0).all()

    def test_garman_klass(self, sample_ohlcv):
        result = garman_klass_vol(
            sample_ohlcv["high"], sample_ohlcv["low"],
            sample_ohlcv["open"], sample_ohlcv["close"],
        )
        assert len(result) == len(sample_ohlcv)

    def test_parkinson(self, sample_ohlcv):
        result = parkinson_vol(sample_ohlcv["high"], sample_ohlcv["low"])
        assert len(result) == len(sample_ohlcv)

    def test_yang_zhang(self, sample_ohlcv):
        result = yang_zhang_vol(
            sample_ohlcv["high"], sample_ohlcv["low"],
            sample_ohlcv["open"], sample_ohlcv["close"],
        )
        assert len(result) == len(sample_ohlcv)


class TestVolume:
    def test_obv(self, sample_ohlcv):
        result = obv(sample_ohlcv["close"], sample_ohlcv["volume"])
        assert len(result) == len(sample_ohlcv)

    def test_vwap_deviation(self, sample_ohlcv):
        result = vwap_deviation(
            sample_ohlcv["high"], sample_ohlcv["low"],
            sample_ohlcv["close"], sample_ohlcv["volume"],
        )
        valid = result.dropna()
        assert len(valid) > 0


class TestComputeAllFeatures:
    def test_all_columns(self, sample_ohlcv):
        result = compute_all_features(sample_ohlcv)
        expected_cols = [
            "rsi_14", "macd", "macd_signal", "macd_histogram",
            "roc_5", "atr_14", "hvol_20", "obv",
            "bb_upper", "bb_lower", "adx",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_no_data_loss(self, sample_ohlcv):
        result = compute_all_features(sample_ohlcv)
        assert len(result) == len(sample_ohlcv)
        assert "close" in result.columns

    def test_empty_df(self):
        result = compute_all_features(pd.DataFrame())
        assert result.empty
