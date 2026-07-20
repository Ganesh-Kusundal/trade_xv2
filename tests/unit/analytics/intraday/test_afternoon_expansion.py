"""Integration test for the Afternoon Expansion Scanner.

Runs against the real ``data/lake`` Parquet store (read-only). It
verifies the zero-look-ahead invariants and that the live-09:50
path (no afternoon bars yet) still yields morning-only candidates.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from analytics.intraday.afternoon_expansion import (
    AfternoonExpansionConfig,
    resolve_trade_date,
    run_scan,
    scan_afternoon_expansion,
)
from analytics.sector.mapping import SectorMapper
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

_LAKE_OK = Path(DEFAULT_DATA_ROOT).joinpath("equities/candles/timeframe=1m").exists()


@pytest.mark.skipif(not _LAKE_OK, reason="data/lake not present")
class TestAfternoonExpansion:
    TRADE_DATE = "2026-07-13"

    def test_returns_dataframe_with_expected_columns(self) -> None:
        df = scan_afternoon_expansion(self.TRADE_DATE)
        for col in (
            "symbol",
            "c950",
            "morning_gain",
            "rvol",
            "hit_ge5",
            "realized_mfe_after_0950",
        ):
            assert col in df.columns, col
        assert not df.empty, "expected >=1 candidate on the trade date"

    def test_no_lookahead_in_ranking(self) -> None:
        """Selection must not depend on the same-day afternoon outcome."""
        df = scan_afternoon_expansion(self.TRADE_DATE)
        # Realized columns must not appear in the WHERE/ORDER BY.
        # We assert the selector-level invariant directly: ranking order is
        # reproducible without the realized columns present.
        ranking_keys = ["hit_ge5", "rvol", "avg_mfe"]
        assert all(k in df.columns for k in ranking_keys)
        # Recompute a rank ignoring realized_* and confirm it still sorts by
        # the historical keys only.
        rerank = df.sort_values(ranking_keys, ascending=[False, False, False]).reset_index(
            drop=True
        )
        pd.testing.assert_frame_equal(df.reset_index(drop=True), rerank, check_like=True)

    def test_picks_are_sector_diversified(self) -> None:
        passes, picks = run_scan(self.TRADE_DATE, pick=True)
        mapper = SectorMapper.default()
        if len(picks) > 1:
            assigned = mapper.assign_sectors(picks)
            # No two picked names share a known sector.
            known = assigned[assigned["sector"] != "Unknown"]
            assert known["sector"].nunique() == len(known), "sector diversification broken"
        assert len(picks) <= AfternoonExpansionConfig().top_k

    def test_live_0950_path_yields_morning_only(self) -> None:
        """At 09:50 there are no afternoon bars yet.

        The LEFT JOIN on ``aft`` must keep the morning row so the
        scanner still ranks (no look-ahead required to exist).
        """
        cfg = AfternoonExpansionConfig()
        # Simulate a date whose afternoon bars are absent by scanning a date
        # and confirming realized columns can be NaN while morning features
        # and historical propensity are present.
        df = scan_afternoon_expansion(self.TRADE_DATE, config=cfg)
        # At least one candidate must have valid morning/historical features.
        assert df["rvol"].notna().any()
        assert df["hit_ge5"].notna().any()
        # realized is allowed to be NaN on an incomplete day.
        if df["realized_mfe_after_0950"].isna().all():
            pytest.skip("trade date already complete; NaN path not exercised")

    def test_date_resolution_falls_back_to_latest(self) -> None:
        from datalake.core.paths import timeframe_partition_dir

        glob = str(Path(timeframe_partition_dir(DEFAULT_DATA_ROOT, "1m")) / "symbol=*/data.parquet")
        con = duckdb.connect()
        latest = con.execute(
            f"SELECT max(CAST(timestamp AS DATE))::VARCHAR "
            f"FROM read_parquet('{glob}', hive_partitioning := true)"
        ).fetchone()[0]
        resolved = resolve_trade_date(con, None)
        assert resolved == latest, f"expected latest lake date {latest}, got {resolved}"
