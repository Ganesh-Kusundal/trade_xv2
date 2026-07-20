"""HistoricalDataLoader._write_parquet must merge, not overwrite.

Regression guard for a real data-loss bug: repair_missing() (the
auto-detect-and-sync entry point) fetches a *shorter* window than the
full history already on disk (e.g. a few days' gap-fill even when the
file holds 6 years). _write_parquet used to blindly overwrite the target
file with whatever was just fetched, silently truncating years of
history. Fixed to read-merge-dedupe-write, mirroring sync_options.py's
existing pattern.
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
    """Returns whatever DataFrame it's configured with on the first call,
    then empty -- mimics gw.history() called once with lookback_days=N
    (single request, no chunking needed) or, when the loader's chunking
    kicks in (lookback_days > max_chunk_days), called multiple times
    with from_date/to_date instead; only the first chunk call returns
    data so tests don't need to worry about date-range slicing."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self._served = False

    def history(
        self, symbol, *, exchange, timeframe, lookback_days=None, from_date=None, to_date=None
    ) -> pd.DataFrame:
        if self._served:
            return self._df.iloc[0:0]
        self._served = True
        return self._df


class TestWriteParquetMerges:
    def test_second_shorter_fetch_does_not_truncate_existing_history(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))

        # Simulate an initial 3-year bulk load.
        old_dates = (
            [f"2022-{m:02d}-01 09:15:00" for m in range(1, 13)]
            + [f"2023-{m:02d}-01 09:15:00" for m in range(1, 13)]
            + [f"2024-{m:02d}-01 09:15:00" for m in range(1, 13)]
        )
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

    def test_catalog_reflects_merged_totals_not_just_latest_fetch(self, tmp_path: Path) -> None:
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
    with existing single-gateway callers (the archived refresh script),
    which keep passing gateway= positionally."""

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


class TestFetchFn:
    """download_symbol/repair_missing accept fetch_fn=(symbol, exchange,
    timeframe, lookback_days) -> DataFrame as the federated-router
    adapter seam (see scripts/sync_datalake.py's _federated_fetch
    closure) -- callers that already have a composer-backed router don't
    need to hand loader.py a raw gateway at all."""

    def test_fetch_fn_is_called_with_expected_args_and_written_through_merge_path(
        self, tmp_path: Path
    ) -> None:
        calls: list[tuple] = []

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            calls.append((symbol, exchange, timeframe, lookback_days))
            return _candles(["2026-01-01 09:15:00"])

        loader = HistoricalDataLoader(root=str(tmp_path))
        result = loader.download_symbol(
            "RELIANCE", years=1, timeframe="1d", exchange="NSE", fetch_fn=fetch_fn
        )
        assert result["rows"] == 1
        assert calls == [("RELIANCE", "NSE", "1d", 365)]

    def test_fetch_fn_takes_precedence_over_gateway_and_gateways(self, tmp_path: Path) -> None:
        fetch_fn_called = []

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            fetch_fn_called.append(True)
            return _candles(["2026-01-01 09:15:00"])

        gw = FakeGateway(_candles(["2020-01-01 09:15:00"]))
        loader = HistoricalDataLoader(root=str(tmp_path))
        loader.download_symbol(
            "RELIANCE",
            gateway=gw,
            years=1,
            timeframe="1d",
            exchange="NSE",
            gateways={"dhan": gw},
            fetch_fn=fetch_fn,
        )
        assert fetch_fn_called == [True]
        assert not gw._served, "gateway.history() must not be called when fetch_fn is given"


class TestRepairMissingExchangePassthrough:
    """repair_missing() must forward exchange= to download_symbol() -- needed
    for symbols that resolve on a different broker exchange than the active
    one (e.g. NIFTY needs exchange="INDEX" on Dhan, not "NSE"). Regression
    guard: repair_missing() used to have no exchange= parameter at all, so
    every call silently fell back to the active exchange's code."""

    def test_exchange_forwarded_on_first_sync(self, tmp_path: Path) -> None:
        calls: list[tuple] = []

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            calls.append((symbol, exchange))
            return _candles(["2026-01-01 09:15:00"])

        loader = HistoricalDataLoader(root=str(tmp_path))
        loader.repair_missing("NIFTY", timeframe="1d", exchange="INDEX", fetch_fn=fetch_fn)
        assert calls == [("NIFTY", "INDEX")]

    def test_exchange_forwarded_on_incremental_repair(self, tmp_path: Path) -> None:
        calls: list[tuple] = []

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            calls.append((symbol, exchange))
            old_dates = [f"2022-{m:02d}-01 09:15:00" for m in range(1, 13)]
            return _candles(old_dates)

        loader = HistoricalDataLoader(root=str(tmp_path))
        loader.repair_missing("NIFTY", timeframe="1d", exchange="INDEX", fetch_fn=fetch_fn)
        calls.clear()

        def fetch_fn2(symbol, exchange, timeframe, lookback_days):
            calls.append((symbol, exchange))
            return _candles(["2025-01-01 09:15:00"])

        loader2 = HistoricalDataLoader(root=str(tmp_path))
        loader2.repair_missing("NIFTY", timeframe="1d", exchange="INDEX", fetch_fn=fetch_fn2)
        assert calls == [("NIFTY", "INDEX")]


class TestRepairMissingLookbackSize:
    """repair_missing() must request only the actual gap, not a hardcoded
    full year. Regression guard: it used to always call
    download_symbol(..., years=1) regardless of how small the real gap
    was, turning a 1-day catch-up sync into a 365-day re-fetch for every
    symbol -- a real production incident (51-minute sync instead of ~2
    minutes)."""

    def test_small_gap_requests_small_lookback_not_a_year(self, tmp_path: Path) -> None:
        import datetime

        calls: list[int] = []

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            calls.append(lookback_days)
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            return _candles([f"{yesterday.isoformat()} 09:15:00"])

        loader = HistoricalDataLoader(root=str(tmp_path))
        loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=fetch_fn)
        calls.clear()

        # Second run: on-disk data now ends yesterday -- a real 1-day gap.
        def fetch_fn2(symbol, exchange, timeframe, lookback_days):
            calls.append(lookback_days)
            today = datetime.date.today()
            return _candles([f"{today.isoformat()} 09:15:00"])

        loader2 = HistoricalDataLoader(root=str(tmp_path))
        loader2.repair_missing("RELIANCE", timeframe="1d", fetch_fn=fetch_fn2)

        assert calls, "expected a fetch for the 1-day gap"
        assert calls[0] < 30, (
            f"lookback_days={calls[0]} for a 1-day gap -- should be a handful "
            "of days, not years=1 (365)"
        )


class TestRepairMissingRaisesOnTotalFailure:
    """repair_missing() must raise when a real gap was detected but every
    broker returned nothing -- not silently return 0. Regression guard: it
    used to return rows=0 in both cases, so a symbol every broker rejects
    (e.g. a delisted/renamed instrument) got folded into sync_datalake.py's
    "Already up to date" bucket instead of "Errors", hiding a real fetch
    failure from the run summary (found via GSPL/JBCHEPHARM in production)."""

    def test_raises_when_gap_exists_but_fetch_returns_nothing(self, tmp_path: Path) -> None:
        import datetime

        def seed_fetch_fn(symbol, exchange, timeframe, lookback_days):
            old = datetime.date.today() - datetime.timedelta(days=20)
            return _candles([f"{old.isoformat()} 09:15:00"])

        loader = HistoricalDataLoader(root=str(tmp_path))
        loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=seed_fetch_fn)

        def failing_fetch_fn(symbol, exchange, timeframe, lookback_days):
            return pd.DataFrame()  # every broker rejected this symbol

        loader2 = HistoricalDataLoader(root=str(tmp_path))
        with pytest.raises(RuntimeError, match="RELIANCE"):
            loader2.repair_missing("RELIANCE", timeframe="1d", fetch_fn=failing_fetch_fn)

    def test_no_raise_when_genuinely_up_to_date(self, tmp_path: Path) -> None:
        import datetime

        def seed_fetch_fn(symbol, exchange, timeframe, lookback_days):
            today = datetime.date.today()
            return _candles([f"{today.isoformat()} 09:15:00"])

        loader = HistoricalDataLoader(root=str(tmp_path))
        loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=seed_fetch_fn)

        def unused_fetch_fn(symbol, exchange, timeframe, lookback_days):
            raise AssertionError("should not be called -- no gap exists")

        loader2 = HistoricalDataLoader(root=str(tmp_path))
        rows = loader2.repair_missing("RELIANCE", timeframe="1d", fetch_fn=unused_fetch_fn)
        assert rows == 0


class TestSymbolPartitionPathRoutesIndices:
    """symbol_partition_path() must route known index symbols (per
    config.indices.is_index) to the indices/ asset segment, not
    equities/ -- regression guard for NIFTY sync writing to the wrong
    on-disk location (equities/ instead of the pre-existing indices/
    layout its data already lived in)."""

    def test_index_symbol_routes_to_indices_asset(self) -> None:
        from datalake.core.paths import symbol_partition_path

        path = symbol_partition_path("data/lake", "NIFTY", "1m")
        assert "/indices/" in str(path)
        assert "/equities/" not in str(path)

    def test_equity_symbol_routes_to_equities_asset(self) -> None:
        from datalake.core.paths import symbol_partition_path

        path = symbol_partition_path("data/lake", "RELIANCE", "1m")
        assert "/equities/" in str(path)
        assert "/indices/" not in str(path)
