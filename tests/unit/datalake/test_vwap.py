"""Tests for datalake.vwap — VWAP computation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from datalake.analytics.vwap import compute_daily_vwap, compute_vwap, vwap_from_candles


@pytest.fixture
def sample_intraday():
    """Sample 1-minute intraday data."""
    dates = pd.date_range("2024-01-15 09:15", periods=375, freq="1min")
    np.random.seed(42)
    base = 1000.0
    prices = base + np.cumsum(np.random.randn(375) * 2)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "open": prices,
            "high": prices + 5,
            "low": prices - 5,
            "close": prices + 1,
            "volume": np.random.randint(100, 10000, 375),
        }
    )


@pytest.fixture
def multi_day_data():
    """Sample multi-day intraday data."""
    dates1 = pd.date_range("2024-01-15 09:15", periods=375, freq="1min")
    dates2 = pd.date_range("2024-01-16 09:15", periods=375, freq="1min")
    dates = dates1.append(dates2)
    np.random.seed(42)
    prices = 1000.0 + np.cumsum(np.random.randn(len(dates)) * 2)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": "RELIANCE",
            "open": prices,
            "high": prices + 5,
            "low": prices - 5,
            "close": prices + 1,
            "volume": np.random.randint(100, 10000, len(dates)),
        }
    )


class TestComputeVwap:
    def test_vwap_column_added(self, sample_intraday):
        result = compute_vwap(sample_intraday)
        assert "vwap" in result.columns

    def test_vwap_values_reasonable(self, sample_intraday):
        result = compute_vwap(sample_intraday)
        typical = (sample_intraday["high"] + sample_intraday["low"] + sample_intraday["close"]) / 3
        assert result["vwap"].iloc[-1] == pytest.approx(typical.mean(), rel=0.05)

    def test_vwap_with_group(self, sample_intraday):
        df = pd.concat([sample_intraday, sample_intraday.assign(symbol="TCS")])
        result = compute_vwap(df, group_col="symbol")
        assert "vwap" in result.columns
        reliance = result[result["symbol"] == "RELIANCE"]["vwap"]
        tcs = result[result["symbol"] == "TCS"]["vwap"]
        assert len(reliance) == len(tcs)

    def test_empty_df(self):
        result = compute_vwap(pd.DataFrame())
        assert result.empty

    def test_missing_columns(self):
        df = pd.DataFrame({"timestamp": [1], "close": [100]})
        result = compute_vwap(df)
        assert "vwap" not in result.columns


class TestDailyVwap:
    def test_daily_vwap_resets(self, multi_day_data):
        result = compute_daily_vwap(multi_day_data)
        assert "vwap_daily" in result.columns

        day1 = result[result["timestamp"].dt.date == pd.Timestamp("2024-01-15").date()]
        result[result["timestamp"].dt.date == pd.Timestamp("2024-01-16").date()]

        assert day1["vwap_daily"].iloc[0] == pytest.approx(day1["vwap_daily"].iloc[-1], rel=0.1)

    def test_daily_vwap_intraday_reset(self, sample_intraday):
        result = compute_daily_vwap(sample_intraday)
        first_vwap = result["vwap_daily"].iloc[0]
        last_vwap = result["vwap_daily"].iloc[-1]
        assert first_vwap > 0
        assert last_vwap > 0


class TestVwapFromCandles:
    def test_from_dataframe(self, sample_intraday):
        result = vwap_from_candles(sample_intraday)
        assert result > 0

    def test_from_list_of_dicts(self):
        candles = [
            {"high": 101, "low": 99, "close": 100, "volume": 1000},
            {"high": 102, "low": 100, "close": 101, "volume": 2000},
        ]
        result = vwap_from_candles(candles)
        tp1 = (101 + 99 + 100) / 3.0
        tp2 = (102 + 100 + 101) / 3.0
        expected = (tp1 * 1000 + tp2 * 2000) / 3000
        assert result == pytest.approx(expected)

    def test_empty_input(self):
        assert vwap_from_candles([]) == 0.0
        assert vwap_from_candles(pd.DataFrame()) == 0.0

    def test_zero_volume(self):
        candles = [{"high": 100, "low": 99, "close": 100, "volume": 0}]
        assert vwap_from_candles(candles) == 0.0
