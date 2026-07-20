"""Tests for datalake.corporate_actions — split/dividend adjustment engine."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from datalake.analytics.corporate_actions import CorporateActionStore


@pytest.fixture
def store(tmp_path):
    """Create a temporary CorporateActionStore."""
    root = tmp_path / "market_data"
    root.mkdir()
    s = CorporateActionStore(root=str(root))
    yield s
    s.close()


@pytest.fixture
def sample_ohlcv():
    """Sample OHLCV data spanning a split date."""
    dates = pd.date_range("2023-06-01", periods=100, freq="1D")
    prices = 1000.0 + np.arange(100, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": "TESTSYM",
            "exchange": "NSE",
            "open": prices,
            "high": prices + 10,
            "low": prices - 10,
            "close": prices,
            "volume": [100000] * 100,
            "oi": [0] * 100,
        }
    )


class TestRecordActions:
    def test_record_split(self, store):
        store.record_split("RELIANCE", date(2023, 7, 1), 2.0, "1:2 split")
        df = store.get_actions("RELIANCE")
        assert len(df) == 1
        assert df.iloc[0]["action_type"] == "split"
        assert df.iloc[0]["ratio"] == 2.0

    def test_record_dividend(self, store):
        store.record_dividend("TCS", date(2023, 9, 15), 25.0, "Interim dividend")
        df = store.get_actions("TCS")
        assert len(df) == 1
        assert df.iloc[0]["action_type"] == "dividend"
        assert df.iloc[0]["dividend_per_share"] == 25.0

    def test_record_bonus(self, store):
        store.record_bonus("INFY", date(2023, 6, 15), 1.0, "1:1 bonus")
        df = store.get_actions("INFY")
        assert len(df) == 1
        assert df.iloc[0]["action_type"] == "bonus"
        assert df.iloc[0]["ratio"] == 1.0

    def test_symbol_normalization(self, store):
        store.record_split("  reliant  ", date(2023, 7, 1), 2.0)
        df = store.get_actions("reliant")
        assert len(df) == 1

    def test_multiple_actions_same_symbol(self, store):
        store.record_split("RELIANCE", date(2022, 1, 1), 2.0)
        store.record_dividend("RELIANCE", date(2022, 7, 1), 10.0)
        store.record_bonus("RELIANCE", date(2023, 1, 1), 1.0)
        df = store.get_actions("RELIANCE")
        assert len(df) == 3


class TestAdjustmentFactors:
    def test_split_factor(self, store):
        store.record_split("RELIANCE", date(2023, 7, 1), 2.0)
        factors = store.get_adjustment_factors("RELIANCE")
        assert len(factors) == 1
        _, factor = factors[0]
        assert factor == pytest.approx(0.5)

    def test_bonus_factor(self, store):
        store.record_bonus("INFY", date(2023, 6, 15), 1.0)
        factors = store.get_adjustment_factors("INFY")
        assert len(factors) == 1
        _, factor = factors[0]
        assert factor == pytest.approx(0.5)

    def test_cumulative_factors(self, store):
        store.record_split("RELIANCE", date(2022, 1, 1), 2.0)
        store.record_bonus("RELIANCE", date(2023, 1, 1), 1.0)
        factors = store.get_adjustment_factors("RELIANCE")
        assert len(factors) == 2
        factor_dates = [f[0] for f in factors]
        normalized = [d.date() if hasattr(d, "date") else d for d in factor_dates]
        assert date(2022, 1, 1) in normalized
        assert date(2023, 1, 1) in normalized

    def test_no_actions_returns_empty(self, store):
        factors = store.get_adjustment_factors("NODATA")
        assert factors == []


class TestApplyAdjustment:
    def test_split_adjusts_pre_split_prices(self, store, sample_ohlcv):
        store.record_split("TESTSYM", date(2023, 8, 1), 2.0)
        adjusted = store.apply_adjustment(sample_ohlcv, "TESTSYM")
        pre_split = adjusted[pd.to_datetime(adjusted["timestamp"]).dt.date < date(2023, 8, 1)]
        post_split = adjusted[pd.to_datetime(adjusted["timestamp"]).dt.date >= date(2023, 8, 1)]
        assert pre_split["close"].max() < post_split["close"].min()

    def test_no_actions_adds_adj_close(self, store, sample_ohlcv):
        adjusted = store.apply_adjustment(sample_ohlcv, "NODATA")
        assert "adj_close" in adjusted.columns
        pd.testing.assert_series_equal(
            adjusted["adj_close"],
            sample_ohlcv["close"].rename("adj_close"),
            check_names=False,
        )

    def test_volume_adjusted_inversely(self, store, sample_ohlcv):
        store.record_split("TESTSYM", date(2023, 8, 1), 2.0)
        adjusted = store.apply_adjustment(sample_ohlcv, "TESTSYM")
        pre_split = adjusted[pd.to_datetime(adjusted["timestamp"]).dt.date < date(2023, 8, 1)]
        assert (pre_split["volume"] > sample_ohlcv["volume"].iloc[0]).all()

    def test_forward_adjustment(self, store, sample_ohlcv):
        store.record_split("TESTSYM", date(2023, 8, 1), 2.0)
        adjusted = store.apply_adjustment(sample_ohlcv, "TESTSYM", direction="forward")
        post_split = adjusted[pd.to_datetime(adjusted["timestamp"]).dt.date >= date(2023, 8, 1)]
        assert post_split["close"].max() < sample_ohlcv["close"].max()


class TestHasActions:
    def test_has_actions_true(self, store):
        store.record_split("RELIANCE", date(2023, 7, 1), 2.0)
        assert store.has_actions("RELIANCE") is True

    def test_has_actions_false(self, store):
        assert store.has_actions("NODATA") is False


class TestSummary:
    def test_summary(self, store):
        store.record_split("RELIANCE", date(2023, 7, 1), 2.0)
        store.record_dividend("TCS", date(2023, 9, 15), 25.0)
        s = store.summary()
        assert s["total_actions"] == 2
        assert s["symbols_with_actions"] == 2
        assert s["by_type"]["split"] == 1
        assert s["by_type"]["dividend"] == 1
