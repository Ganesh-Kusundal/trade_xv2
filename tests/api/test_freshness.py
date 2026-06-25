"""Tests for data freshness validation."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from api.freshness import FreshnessResult, check_data_freshness


class TestDataFreshness:
    """Test data freshness checks."""

    def test_fresh_intraday_data(self):
        """Today's data should be fresh for intraday timeframes."""
        today = date.today()
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([today]),
                "open": [100.0],
                "close": [101.0],
            }
        )

        result = check_data_freshness(df, "1m")
        assert result.is_stale is False
        assert result.status == "FRESH"
        assert result.days_old == 0

    def test_stale_intraday_data(self):
        """Yesterday's data should be stale for 1m timeframe."""
        yesterday = date.today() - timedelta(days=1)
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([yesterday]),
                "open": [100.0],
                "close": [101.0],
            }
        )

        result = check_data_freshness(df, "1m")
        assert result.is_stale is True
        assert result.status == "STALE"
        assert result.days_old == 1

    def test_fresh_daily_data(self):
        """2-day-old data should be fresh for 1d timeframe."""
        two_days_ago = date.today() - timedelta(days=2)
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([two_days_ago]),
                "open": [100.0],
                "close": [101.0],
            }
        )

        result = check_data_freshness(df, "1d")
        assert result.is_stale is False  # Threshold is 2 days
        assert result.status == "FRESH"

    def test_stale_daily_data(self):
        """5-day-old data should be stale for 1d timeframe."""
        five_days_ago = date.today() - timedelta(days=5)
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([five_days_ago]),
                "open": [100.0],
                "close": [101.0],
            }
        )

        result = check_data_freshness(df, "1d")
        assert result.is_stale is True
        assert result.days_old == 5

    def test_fresh_weekly_data(self):
        """5-day-old data should be fresh for 1w timeframe."""
        five_days_ago = date.today() - timedelta(days=5)
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([five_days_ago]),
                "open": [100.0],
                "close": [101.0],
            }
        )

        result = check_data_freshness(df, "1w")
        assert result.is_stale is False  # Threshold is 7 days
        assert result.status == "FRESH"

    def test_empty_dataframe_is_stale(self):
        """Empty DataFrame should be marked as stale/missing."""
        df = pd.DataFrame()
        result = check_data_freshness(df, "1m")
        assert result.is_stale is True
        assert result.status == "MISSING"
        assert result.last_update is None

    def test_none_dataframe_is_stale(self):
        """None DataFrame should be marked as stale/missing."""
        result = check_data_freshness(None, "1m")  # type: ignore
        assert result.is_stale is True
        assert result.status == "MISSING"

    def test_4h_timeframe_allows_1_day_old(self):
        """4h timeframe allows data up to 1 day old."""
        yesterday = date.today() - timedelta(days=1)
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([yesterday]),
                "open": [100.0],
            }
        )

        result = check_data_freshness(df, "4h")
        assert result.is_stale is False  # Threshold is 1 day
        assert result.days_old == 1

    def test_custom_timestamp_column(self):
        """Should support custom timestamp column name."""
        today = date.today()
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime([today]),
                "open": [100.0],
            }
        )

        result = check_data_freshness(df, "1m", timestamp_col="datetime")
        assert result.is_stale is False

    def test_uses_index_if_no_timestamp_column(self):
        """Should use DatetimeIndex if timestamp column missing."""
        today = date.today()
        df = pd.DataFrame(
            {
                "open": [100.0],
            },
            index=pd.DatetimeIndex([today]),
        )

        result = check_data_freshness(df, "1m")
        assert result.is_stale is False

    def test_freshness_result_has_all_fields(self):
        """FreshnessResult should contain all expected fields."""
        today = date.today()
        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime([today]),
                "open": [100.0],
            }
        )

        result = check_data_freshness(df, "5m")
        assert isinstance(result, FreshnessResult)
        assert hasattr(result, "is_stale")
        assert hasattr(result, "last_update")
        assert hasattr(result, "days_old")
        assert hasattr(result, "threshold_days")
        assert hasattr(result, "status")
        assert result.threshold_days == 0  # 5m threshold
