"""Tests for analytics.stocks.find_levels (support/resistance detection)."""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from analytics.stocks.find_levels import (
    _cluster_levels,
    _find_pivots,
    find_support_resistance,
)


def _make_daily_df(rows: list[dict]) -> pd.DataFrame:
    """Build a daily OHLC DataFrame from a list of dicts."""
    return pd.DataFrame(rows)


def _make_catalog_with_daily(catalog_path, daily_rows: list[dict]) -> None:
    """Create a temp DuckDB with v_daily_summary populated from rows."""
    c = duckdb.connect(str(catalog_path))
    c.execute("""
        CREATE TABLE v_daily_summary (
            trade_date DATE,
            symbol VARCHAR,
            day_open DOUBLE,
            day_high DOUBLE,
            day_low DOUBLE,
            day_close DOUBLE,
            day_volume BIGINT,
            day_oi BIGINT
        )
    """)
    if daily_rows:
        import datetime
        for row in daily_rows:
            # DuckDB inserts directly from dicts using prepared statement
            c.execute(
                "INSERT INTO v_daily_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    row["trade_date"],
                    row["symbol"],
                    row["day_open"],
                    row["day_high"],
                    row["day_low"],
                    row["day_close"],
                    row["day_volume"],
                    row.get("day_oi", 0),
                ]
            )
    c.close()


# ============================================================
# Tests for _find_pivots
# ============================================================


class TestFindPivots:
    def test_simple_pivot_high(self) -> None:
        """Bar 3 is higher than bars 0-2 and 4-6 → resistance at bar 3."""
        daily = _make_daily_df(
            [
                {"date": date(2026, 1, i + 1), "high": 100.0, "low": 90.0, "close": 95.0}
                for i in range(7)
            ]
        )
        daily.loc[3, "high"] = 120.0  # pivot high
        daily.loc[3, "low"] = 115.0

        _, resistances = _find_pivots(daily, window=2)
        assert len(resistances) == 1
        assert resistances[0] == (daily.loc[3, "date"], 120.0)

    def test_simple_pivot_low(self) -> None:
        """Bar 3 is lower than bars 0-2 and 4-6 → support at bar 3."""
        daily = _make_daily_df(
            [
                {"date": date(2026, 1, i + 1), "high": 100.0, "low": 90.0, "close": 95.0}
                for i in range(7)
            ]
        )
        daily.loc[3, "low"] = 80.0  # pivot low

        supports, _ = _find_pivots(daily, window=2)
        assert len(supports) == 1
        assert supports[0] == (daily.loc[3, "date"], 80.0)

    def test_no_pivots_in_small_data(self) -> None:
        daily = _make_daily_df(
            [
                {"date": date(2026, 1, i + 1), "high": 100.0, "low": 90.0, "close": 95.0}
                for i in range(3)  # < 2*window+1 = 5
            ]
        )
        supports, resistances = _find_pivots(daily, window=2)
        assert supports == []
        assert resistances == []

    def test_pivot_window_excludes_self(self) -> None:
        """A bar higher than ITSELF is not a pivot (window excludes i)."""
        daily = _make_daily_df(
            [
                {"date": date(2026, 1, i + 1), "high": 100.0, "low": 90.0, "close": 95.0}
                for i in range(5)
            ]
        )
        # All bars same price → no pivots (each bar is "equal" to its window)
        supports, resistances = _find_pivots(daily, window=2)
        assert supports == []
        assert resistances == []


# ============================================================
# Tests for _cluster_levels
# ============================================================


class TestClusterLevels:
    def test_empty_pivots(self) -> None:
        assert _cluster_levels([]) == []

    def test_single_pivot(self) -> None:
        pivots = [(date(2026, 1, 1), 100.0)]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert len(levels) == 1
        assert levels[0].price == 100.0
        assert levels[0].touches == 1

    def test_clusters_nearby_pivots(self) -> None:
        """Two pivots within 1% of each other → one cluster, 2 touches."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 5), 100.5),  # within 1% of 100.0
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert len(levels) == 1
        assert levels[0].touches == 2
        assert levels[0].price == 100.25  # average

    def test_separates_distant_pivots(self) -> None:
        """Two pivots >1% apart → two clusters."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 5), 105.0),  # 5% away → separate cluster
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert len(levels) == 2

    def test_levels_sorted_by_touches_then_price(self) -> None:
        """Stronger level (more touches) comes first."""
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 2), 100.1),
            (date(2026, 1, 3), 100.2),  # 3-touches cluster at 100
            (date(2026, 1, 4), 200.0),
            (date(2026, 1, 5), 200.1),  # 2-touches cluster at 200
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert levels[0].touches == 3
        assert levels[0].price == pytest.approx(100.1, abs=0.05)
        assert levels[1].touches == 2

    def test_last_touch_date_tracked(self) -> None:
        pivots = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 5), 100.3),
        ]
        levels = _cluster_levels(pivots, tolerance=0.01)
        assert levels[0].last_touch == date(2026, 1, 5)


# ============================================================
# Tests for find_support_resistance (end-to-end with tmp catalog)
# ============================================================


class TestFindSupportResistance:
    def test_empty_data_returns_empty(self, tmp_path) -> None:
        cat = tmp_path / "cat.duckdb"
        _make_catalog_with_daily(cat, [])
        result = find_support_resistance("RELIANCE", days=60, catalog_path=cat)
        assert result == {"support": [], "resistance": []}

    def test_finds_pivots_in_synthetic_data(self, tmp_path) -> None:
        """Build 30 days of data with one clear pivot high and one clear pivot low."""
        rows = []
        for i in range(30):
            rows.append(
                {
                    "trade_date": date(2026, 1, 1) + timedelta(days=i),
                    "symbol": "RELIANCE",
                    "day_open": 100.0,
                    "day_high": 102.0,
                    "day_low": 98.0,
                    "day_close": 100.0,
                    "day_volume": 1000,
                    "day_oi": 0,
                }
            )
        # Inject a clear pivot high at day 15
        rows[15]["day_high"] = 130.0
        # Inject a clear pivot low at day 20
        rows[20]["day_low"] = 80.0

        cat = tmp_path / "cat.duckdb"
        _make_catalog_with_daily(cat, rows)

        result = find_support_resistance("RELIANCE", days=365, catalog_path=cat)
        # Should find at least the support (low pivot at 80) and resistance (high at 130)
        assert any(lvl.price == 80.0 for lvl in result["support"])
        assert any(lvl.price == 130.0 for lvl in result["resistance"])

    def test_top_n_respected(self, tmp_path) -> None:
        """With 5 distinct pivot levels, top_n=2 returns only 2."""
        rows = []
        for i in range(30):
            rows.append(
                {
                    "trade_date": date(2026, 1, 1) + timedelta(days=i),
                    "symbol": "RELIANCE",
                    "day_open": 100.0,
                    "day_high": 102.0,
                    "day_low": 98.0,
                    "day_close": 100.0,
                    "day_volume": 1000,
                    "day_oi": 0,
                }
            )
        # Inject 5 distinct resistance pivots
        for pivot_idx, pivot_high in [
            (5, 130.0),
            (10, 140.0),
            (15, 150.0),
            (20, 160.0),
            (25, 170.0),
        ]:
            rows[pivot_idx]["day_high"] = pivot_high

        cat = tmp_path / "cat.duckdb"
        _make_catalog_with_daily(cat, rows)

        result = find_support_resistance("RELIANCE", days=365, top_n=2, catalog_path=cat)
        assert len(result["resistance"]) == 2
        # The 2 strongest (each touched once) — sorted by price
        prices = [lvl.price for lvl in result["resistance"]]
        assert prices == sorted(prices)

    def test_date_filter(self, tmp_path) -> None:
        """Only bars within the days window are considered.

        Build 40 days of data ending TODAY. With days=30:
        - Day 35 pivot (5 days before window start) → EXCLUDED
        - Day 25 pivot (within window) → INCLUDED
        """
        today = date.today()
        rows = []
        for i in range(40):
            rows.append(
                {
                    "trade_date": today
                    - timedelta(days=39 - i),  # day 0 = 39 days ago, day 39 = today
                    "symbol": "RELIANCE",
                    "day_open": 100.0,
                    "day_high": 102.0,
                    "day_low": 98.0,
                    "day_close": 100.0,
                    "day_volume": 1000,
                    "day_oi": 0,
                }
            )
        # Day 5 pivot (34 days ago) — should be EXCLUDED (outside 30-day window)
        rows[5]["day_high"] = 200.0
        # Day 25 pivot (14 days ago) — should be INCLUDED
        rows[25]["day_high"] = 150.0

        cat = tmp_path / "cat.duckdb"
        _make_catalog_with_daily(cat, rows)

        result = find_support_resistance(
            "RELIANCE",
            days=30,
            catalog_path=cat,
        )
        prices = [lvl.price for lvl in result["resistance"]]
        assert 150.0 in prices, f"Expected 150.0 in {prices}"
        assert 200.0 not in prices, f"Old pivot 200.0 leaked: {prices}"

    def test_symbol_normalization(self, tmp_path) -> None:
        """Symbol with -EQ suffix should match the normalized form."""
        rows = [
            {
                "trade_date": date(2026, 1, 1),
                "symbol": "RELIANCE",  # stored without suffix
                "day_open": 100.0,
                "day_high": 102.0,
                "day_low": 98.0,
                "day_close": 100.0,
                "day_volume": 1000,
                "day_oi": 0,
            }
        ]
        cat = tmp_path / "cat.duckdb"
        _make_catalog_with_daily(cat, rows)

        # Should work with -EQ suffix (normalized away)
        result = find_support_resistance("RELIANCE-EQ", days=60, catalog_path=cat)
        # Won't find pivots (not enough data) but should not error
        assert "support" in result
        assert "resistance" in result
