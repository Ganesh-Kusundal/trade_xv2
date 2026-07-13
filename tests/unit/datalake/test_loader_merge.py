"""HistoricalDataLoader._write_parquet must merge, not overwrite.

Regression guard for a real data-loss bug: repair_missing() (the
auto-detect-and-sync entry point) and IncrementalUpdater.update_daily()
both fetch a *shorter* window than the full history already on disk
(e.g. repair_missing fetches years=1 even when the file holds 6 years).
_write_parquet used to blindly overwrite the target file with whatever
was just fetched, silently truncating years of history. Fixed to
read-merge-dedupe-write, mirroring sync_options.py's existing pattern.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datalake.ingestion.loader import HistoricalDataLoader


def _candles(dates: list[str], base_price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(dates),
            "symbol": ["RELIANCE"] * len(dates),
            "exchange": ["NSE"] * len(dates),
            "open": [base_price] * len(dates),
            "high": [base_price + 1] * len(dates),
            "low": [base_price - 1] * len(dates),
            "close": [base_price + 0.5] * len(dates),
            "volume": [1000] * len(dates),
            "oi": [0] * len(dates),
        }
    )


class FakeGateway:
    """Returns whatever DataFrame it's configured with, mimicking
    gw.history(symbol, exchange=, timeframe=, lookback_days=)."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def history(self, symbol, *, exchange, timeframe, lookback_days) -> pd.DataFrame:
        return self._df


class TestWriteParquetMerges:
    def test_second_shorter_fetch_does_not_truncate_existing_history(
        self, tmp_path: Path
    ) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))

        # Simulate an initial 3-year bulk load.
        old_dates = [f"2022-{m:02d}-01 09:15:00" for m in range(1, 13)] + [
            f"2023-{m:02d}-01 09:15:00" for m in range(1, 13)
        ] + [f"2024-{m:02d}-01 09:15:00" for m in range(1, 13)]
        gw1 = FakeGateway(_candles(old_dates))
        result1 = loader.download_symbol("RELIANCE", gw1, years=3, timeframe="1d", exchange="NSE")
        assert result1["rows"] == len(old_dates)

        # Simulate a later incremental repair with a *much shorter*
        # window (repair_missing's years=1 pattern) that only covers 2025.
        new_dates = [f"2025-{m:02d}-01 09:15:00" for m in range(1, 4)]
        gw2 = FakeGateway(_candles(new_dates, base_price=200.0))
        loader.download_symbol("RELIANCE", gw2, years=1, timeframe="1d", exchange="NSE")

        # The file on disk must still contain the original 2022-2024
        # history, not just the 2025 incremental fetch.
        written = pd.read_parquet(loader._parquet_path("RELIANCE", "1d"))
        assert len(written) == len(old_dates) + len(new_dates)
        years_present = pd.to_datetime(written["timestamp"]).dt.year.unique()
        assert set(years_present) == {2022, 2023, 2024, 2025}

    def test_overlapping_timestamp_keeps_latest_value(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))

        gw1 = FakeGateway(_candles(["2026-01-01 09:15:00"], base_price=100.0))
        loader.download_symbol("RELIANCE", gw1, years=1, timeframe="1d", exchange="NSE")

        # Same timestamp, revised price (e.g. broker correction).
        gw2 = FakeGateway(_candles(["2026-01-01 09:15:00"], base_price=999.0))
        loader.download_symbol("RELIANCE", gw2, years=1, timeframe="1d", exchange="NSE")

        written = pd.read_parquet(loader._parquet_path("RELIANCE", "1d"))
        assert len(written) == 1
        assert written["open"].iloc[0] == pytest.approx(999.0)

    def test_catalog_reflects_merged_totals_not_just_latest_fetch(
        self, tmp_path: Path
    ) -> None:
        """register_symbol() must describe the merged on-disk file, or
        catalog metadata silently drifts from reality after any
        incremental (shorter-window) sync."""
        from datalake.storage.catalog import DataCatalog

        catalog = DataCatalog(str(tmp_path / "catalog.duckdb"))
        loader = HistoricalDataLoader(root=str(tmp_path), catalog=catalog)

        old_dates = [f"2022-{m:02d}-01 09:15:00" for m in range(1, 13)]
        loader.download_symbol(
            "RELIANCE", FakeGateway(_candles(old_dates)), years=3, timeframe="1d", exchange="NSE"
        )
        new_dates = ["2025-01-01 09:15:00"]
        loader.download_symbol(
            "RELIANCE",
            FakeGateway(_candles(new_dates)),
            years=1,
            timeframe="1d",
            exchange="NSE",
        )

        row = catalog.conn.execute(
            "SELECT first_date, last_date, total_rows FROM symbols WHERE symbol = 'RELIANCE'"
        ).fetchone()
        first_date, last_date, total_rows = row
        assert str(first_date) == "2022-01-01"
        assert str(last_date) == "2025-01-01"
        assert total_rows == len(old_dates) + len(new_dates)


class TestGatewaysAutoSelect:
    """download_symbol/download_universe/repair_missing accept a
    gateways={broker_id: gw} dict as an alternative to a single gateway=,
    auto-selecting via select_historical_source() -- backward compatible
    with existing single-gateway callers (IncrementalUpdater, the
    archived refresh script), which keep passing gateway= positionally."""

    def test_download_symbol_auto_selects_from_gateways_dict(self, tmp_path: Path) -> None:
        from dataclasses import dataclass

        @dataclass
        class FakeWindow:
            timeframe: str
            max_lookback_days: int
            max_chunk_days: int

        class FakeCaps:
            def __init__(self, windows):
                self.historical_windows = windows

        class SelectableFakeGateway(FakeGateway):
            def __init__(self, df, windows):
                super().__init__(df)
                self._caps = FakeCaps(windows)

            def capabilities(self):
                return self._caps

        long_range = SelectableFakeGateway(
            _candles(["2022-01-01 09:15:00"]), [FakeWindow("1d", 3650, 365)]
        )
        short_range = SelectableFakeGateway(
            _candles(["2022-01-01 09:15:00"]), [FakeWindow("1d", 30, 30)]
        )

        loader = HistoricalDataLoader(root=str(tmp_path))
        result = loader.download_symbol(
            "RELIANCE",
            years=1,
            timeframe="1d",
            exchange="NSE",
            gateways={"short": short_range, "long": long_range},
        )
        assert result["rows"] == 1

    def test_download_symbol_requires_gateway_or_gateways(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))
        with pytest.raises(ValueError, match="gateway"):
            loader.download_symbol("RELIANCE", years=1, timeframe="1d", exchange="NSE")
