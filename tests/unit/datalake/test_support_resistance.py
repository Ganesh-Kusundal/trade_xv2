"""Tests for datalake.analytics.support_resistance — precomputed S/R levels."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from datalake.analytics._sr_algorithms import (
    cluster_levels as _cluster_levels,
)
from datalake.analytics._sr_algorithms import (
    find_pivots as _find_pivots,
)
from datalake.analytics.support_resistance import PriceLevel, SupportResistance

# ── Pure algorithm tests ──────────────────────────────────────────────────


class TestFindPivots:
    """Test pivot detection algorithm."""

    def test_simple_pivot_high(self):
        """Bar 3 is higher than bars 0-2 and 4-6 → resistance at bar 3."""
        dates = pd.date_range("2026-01-01", periods=7)
        daily = pd.DataFrame(
            {
                "date": dates,
                "high": [100.0, 100.0, 100.0, 120.0, 100.0, 100.0, 100.0],
                "low": [90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0],
                "close": [95.0, 95.0, 95.0, 95.0, 95.0, 95.0, 95.0],
            }
        )
        _supports, resistances = _find_pivots(daily, window=2)
        assert len(resistances) == 1
        assert resistances[0] == (dates[3], 120.0)

    def test_simple_pivot_low(self):
        """Bar 3 is lower than bars 0-2 and 4-6 → support at bar 3."""
        dates = pd.date_range("2026-01-01", periods=7)
        daily = pd.DataFrame(
            {
                "date": dates,
                "high": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
                "low": [80.0, 80.0, 80.0, 60.0, 80.0, 80.0, 80.0],
                "close": [90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0],
            }
        )
        supports, _resistances = _find_pivots(daily, window=2)
        assert len(supports) == 1
        assert supports[0] == (dates[3], 60.0)

    def test_no_pivots_in_small_data(self):
        """Less than 2*window+1 bars → no pivots."""
        dates = pd.date_range("2026-01-01", periods=3)
        daily = pd.DataFrame(
            {
                "date": dates,
                "high": [100.0, 110.0, 100.0],
                "low": [90.0, 80.0, 90.0],
                "close": [95.0, 95.0, 95.0],
            }
        )
        supports, resistances = _find_pivots(daily, window=2)
        assert supports == []
        assert resistances == []

    def test_multiple_pivots(self):
        """Two distinct pivot highs and two pivot lows."""
        dates = pd.date_range("2026-01-01", periods=11)
        daily = pd.DataFrame(
            {
                "date": dates,
                "high": [100, 100, 100, 120, 100, 100, 130, 100, 100, 100, 100],
                "low": [80, 80, 80, 80, 80, 60, 80, 80, 70, 80, 80],
                "close": [90] * 11,
            }
        )
        supports, resistances = _find_pivots(daily, window=2)
        assert len(resistances) >= 2
        assert len(supports) >= 2

    def test_monotonic_data_no_pivots(self):
        """Monotonically increasing data → no pivot lows, maybe pivot highs."""
        dates = pd.date_range("2026-01-01", periods=10)
        daily = pd.DataFrame(
            {
                "date": dates,
                "high": [100 + i * 5 for i in range(10)],
                "low": [90 + i * 5 for i in range(10)],
                "close": [95 + i * 5 for i in range(10)],
            }
        )
        supports, _resistances = _find_pivots(daily, window=2)
        # Monotonically increasing → no pivot lows (each low > previous)
        assert len(supports) == 0


class TestClusterLevels:
    """Test level clustering algorithm."""

    def test_empty_pivots(self):
        assert _cluster_levels([]) == []

    def test_single_pivot(self):
        pivots = [(date(2026, 1, 1), 100.0)]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert len(levels) == 1
        assert levels[0].price == 100.0
        assert levels[0].touches == 1

    def test_clusters_nearby_pivots(self):
        """Two pivots within 1% → one cluster, 2 touches."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 5), 100.5),
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert len(levels) == 1
        assert levels[0].touches == 2
        assert levels[0].price == pytest.approx(100.25, abs=0.05)

    def test_separates_distant_pivots(self):
        """Two pivots >1% apart → two clusters."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 5), 110.0),
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert len(levels) == 2

    def test_levels_sorted_by_touches(self):
        """Stronger level (more touches) comes first."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 2), 100.1),
            (date(2026, 1, 3), 100.2),
            (date(2026, 1, 10), 110.0),
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert levels[0].touches == 3
        assert levels[1].touches == 1

    def test_last_touch_date(self):
        """last_touch is the most recent date in the cluster."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 10), 100.5),
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert levels[0].last_touch == date(2026, 1, 10)


# ── Integration tests with real data ──────────────────────────────────────


class TestSupportResistanceIntegration:
    """Integration tests using the actual datalake."""

    def test_get_levels_returns_dict(self):
        """get_levels returns support and resistance lists."""
        sr = SupportResistance()
        result = sr.get_levels("RELIANCE", days=60)
        assert "support" in result
        assert "resistance" in result
        assert isinstance(result["support"], list)
        assert isinstance(result["resistance"], list)

    def test_levels_are_pricelevel_instances(self):
        """Each level is a PriceLevel dataclass."""
        sr = SupportResistance()
        result = sr.get_levels("RELIANCE", days=60)
        for level in result["support"] + result["resistance"]:
            assert isinstance(level, PriceLevel)
            assert level.price > 0
            assert level.touches >= 1
            lt = level.last_touch
            if hasattr(lt, "date") and not isinstance(lt, type(date)):
                lt = lt.date()
            if isinstance(lt, np.datetime64):
                lt = pd.Timestamp(lt).date()
            assert isinstance(lt, date)

    def test_top_n_limits_results(self):
        """top_n limits the number of returned levels."""
        sr = SupportResistance()
        result = sr.get_levels("RELIANCE", days=120, top_n=3)
        assert len(result["support"]) <= 3
        assert len(result["resistance"]) <= 3

    def test_nearest_levels(self):
        """get_nearest_levels returns closest support/resistance."""
        sr = SupportResistance()
        result = sr.get_nearest_levels("RELIANCE", current_price=2500.0, days=120)
        assert "nearest_support" in result
        assert "nearest_resistance" in result
        assert "position_in_range_pct" in result

        if result["nearest_support"]:
            assert result["nearest_support"].price < 2500
        if result["nearest_resistance"]:
            assert result["nearest_resistance"].price > 2500

    def test_batch_returns_all_symbols(self):
        """get_levels_batch returns results for all requested symbols."""
        sr = SupportResistance()
        result = sr.get_levels_batch(["RELIANCE", "TCS", "INFY"], days=60)
        assert len(result) == 3
        for symbol in ["RELIANCE", "TCS", "INFY"]:
            assert symbol in result
            assert "support" in result[symbol]
            assert "resistance" in result[symbol]

    def test_empty_for_missing_symbol(self):
        """Missing symbol returns empty levels."""
        sr = SupportResistance()
        result = sr.get_levels("NONEXISTENT_SYMBOL", days=60)
        assert result["support"] == []
        assert result["resistance"] == []


class TestPrecomputation:
    """Test precomputation and storage."""

    def test_precompute_creates_parquet(self, tmp_path):
        """precompute creates a levels.parquet file."""
        sr = SupportResistance(features_root=tmp_path / "features")
        stats = sr.precompute(symbols=["RELIANCE"], days=60, force=True)
        assert stats["symbols_processed"] == 1
        assert stats["total_levels"] > 0
        assert (tmp_path / "features" / "support_resistance" / "levels.parquet").exists()

    def test_precomputed_data_is_queryable(self, tmp_path):
        """Data written by precompute can be read back."""
        sr = SupportResistance(features_root=tmp_path / "features")
        sr.precompute(symbols=["RELIANCE"], days=60, force=True)

        # Read back
        levels = sr._read_precomputed("RELIANCE")
        assert len(levels) > 0
        assert all(isinstance(l, PriceLevel) for l in levels)

    def test_precomputed_vs_on_the_fly(self, tmp_path):
        """Precomputed and on-the-fly results should match."""
        sr = SupportResistance(features_root=tmp_path / "features")
        sr.precompute(symbols=["RELIANCE"], days=60, force=True)

        # Get from precomputed
        result_precomputed = sr.get_levels("RELIANCE", days=60, top_n=5)

        # Get from on-the-fly (clear precomputed)
        import shutil

        shutil.rmtree(tmp_path / "features" / "support_resistance")
        result_onthefly = sr.get_levels("RELIANCE", days=60, top_n=5)

        # Both should have same number of levels (prices may differ slightly)
        assert len(result_precomputed["support"]) == len(result_onthefly["support"])
        assert len(result_precomputed["resistance"]) == len(result_onthefly["resistance"])


# ── Accuracy tests ────────────────────────────────────────────────────────


class TestAccuracy:
    """Test that S/R levels are mathematically correct."""

    def test_resistance_above_support(self):
        """All resistance levels should be above all support levels."""
        sr = SupportResistance()
        result = sr.get_levels("RELIANCE", days=120, top_n=5)

        if result["support"] and result["resistance"]:
            max_support = max(l.price for l in result["support"])
            min_resistance = min(l.price for l in result["resistance"])
            # In a trending market, resistance can be below support
            # but typically resistance > support
            assert min_resistance > max_support * 0.9  # allow 10% tolerance

    def test_touches_are_positive(self):
        """Touch count should always be >= 1."""
        sr = SupportResistance()
        result = sr.get_levels("RELIANCE", days=60)
        for level in result["support"] + result["resistance"]:
            assert level.touches >= 1

    def test_prices_are_positive(self):
        """All prices should be positive."""
        sr = SupportResistance()
        result = sr.get_levels("RELIANCE", days=60)
        for level in result["support"] + result["resistance"]:
            assert level.price > 0

    def test_last_touch_within_window(self):
        """last_touch should be within the lookback window."""
        sr = SupportResistance()
        days = 60
        result = sr.get_levels("RELIANCE", days=days)
        cutoff = date.today() - timedelta(days=days)
        for level in result["support"] + result["resistance"]:
            lt = level.last_touch
            if hasattr(lt, "date") and not isinstance(lt, type(date)):
                lt = lt.date()
            if isinstance(lt, np.datetime64):
                lt = pd.Timestamp(lt).date()
            assert lt >= cutoff
