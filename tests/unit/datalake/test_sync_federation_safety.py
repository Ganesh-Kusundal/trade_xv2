"""Federated datalake sync safety: degraded fetch gating, catalog fast path, health gate."""

from __future__ import annotations

import datetime
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from application.data.provenance import ProvenanceLedger
from application.data.sync_fetch_strategy import require_complete_federated_fetch
from datalake.ingestion.loader import HistoricalDataLoader
from datalake.mcp.tools import DatalakeTools
from datalake.storage.catalog import DataCatalog
from domain.candles.historical import DateRange, Gap, HistoricalSeries, InstrumentRef
from tests.unit.datalake.test_loader_merge import FakeGateway, _candles


def _empty_series(*, gaps: list[Gap] | None = None) -> HistoricalSeries:
    return HistoricalSeries(
        bars=[],
        coverage=DateRange(start=date.today(), end=date.today()),
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        timeframe="1m",
        gaps=gaps or [],
    )


class TestRequireCompleteFederatedFetch:
    def test_degraded_ledger_raises(self) -> None:
        ledger = ProvenanceLedger(request_id="r1", instrument="RELIANCE", timeframe="1m")
        ledger.mark_degraded("chunk_failed")
        series = _empty_series()
        with pytest.raises(RuntimeError, match="federated fetch degraded"):
            require_complete_federated_fetch("RELIANCE", series, ledger)

    def test_gaps_raise_even_when_ledger_not_degraded(self) -> None:
        ledger = ProvenanceLedger(request_id="r1", instrument="RELIANCE", timeframe="1m")
        gaps = [Gap(start=date.today(), end=date.today(), reason="missing_chunk")]
        series = _empty_series(gaps=gaps)
        with pytest.raises(RuntimeError, match="gaps=1"):
            require_complete_federated_fetch("RELIANCE", series, ledger)

    def test_degraded_fetch_fn_does_not_write_parquet(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))
        old_dates = [
            (datetime.date.today() - datetime.timedelta(days=5)).isoformat() + " 09:15:00"
        ]
        loader.download_symbol(
            "RELIANCE",
            FakeGateway(_candles(old_dates)),
            years=1,
            timeframe="1d",
            exchange="NSE",
        )
        path = tmp_path / "equities" / "candles" / "timeframe=1d" / "symbol=RELIANCE" / "data.parquet"
        before = path.read_bytes()

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            series = _empty_series(gaps=[Gap(start=date.today(), end=date.today())])
            ledger = ProvenanceLedger(request_id="r1", instrument=symbol, timeframe=timeframe)
            require_complete_federated_fetch(symbol, series, ledger)
            return _candles([datetime.date.today().isoformat() + " 09:15:00"])

        with pytest.raises(RuntimeError, match="federated fetch degraded"):
            loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=fetch_fn)
        assert path.read_bytes() == before


class TestCatalogFastPath:
    def test_skips_parquet_read_when_catalog_stale(self, tmp_path: Path, monkeypatch) -> None:
        from datalake.core.nse_calendar import trading_days_between

        read_calls: list[tuple] = []
        original_read = pd.read_parquet

        def tracking_read(*args, **kwargs):
            read_calls.append(args)
            return original_read(*args, **kwargs)

        monkeypatch.setattr(pd, "read_parquet", tracking_read)

        catalog = DataCatalog(str(tmp_path))
        loader = HistoricalDataLoader(root=str(tmp_path), catalog=catalog)
        today = datetime.date.today()
        history_days = trading_days_between(today - datetime.timedelta(days=10), today - datetime.timedelta(days=1))
        stale_dates = [f"{d.isoformat()} 09:15:00" for d in history_days]
        loader.download_symbol(
            "RELIANCE",
            FakeGateway(_candles(stale_dates)),
            years=1,
            timeframe="1d",
            exchange="NSE",
        )
        read_calls.clear()

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            return _candles([f"{today.isoformat()} 09:15:00"])

        loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=fetch_fn)
        # Tail uses catalog fast path (no gap-detection read); phase B scans once;
        # merge-write reads once when tail fetch returns new rows.
        assert len(read_calls) == 2, (
            f"expected 2 parquet reads (internal scan + merge), got {len(read_calls)}"
        )

    def test_falls_through_for_today_last_date(self, tmp_path: Path, monkeypatch) -> None:
        read_calls: list[tuple] = []
        original_read = pd.read_parquet

        def tracking_read(*args, **kwargs):
            read_calls.append(args)
            return original_read(*args, **kwargs)

        monkeypatch.setattr(pd, "read_parquet", tracking_read)

        catalog = DataCatalog(str(tmp_path))
        loader = HistoricalDataLoader(root=str(tmp_path), catalog=catalog)
        today = datetime.date.today().isoformat()
        loader.download_symbol(
            "RELIANCE",
            FakeGateway(_candles([f"{today} 09:15:00"])),
            years=1,
            timeframe="1d",
            exchange="NSE",
        )
        read_calls.clear()
        loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=lambda *a, **k: _candles([]))
        assert len(read_calls) >= 1

    def test_falls_through_when_no_catalog_row(self, tmp_path: Path, monkeypatch) -> None:
        read_calls: list[tuple] = []
        original_read = pd.read_parquet

        def tracking_read(*args, **kwargs):
            read_calls.append(args)
            return original_read(*args, **kwargs)

        monkeypatch.setattr(pd, "read_parquet", tracking_read)

        loader = HistoricalDataLoader(root=str(tmp_path))
        stale = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        loader.download_symbol(
            "RELIANCE",
            FakeGateway(_candles([f"{stale} 09:15:00"])),
            years=1,
            timeframe="1d",
            exchange="NSE",
        )
        read_calls.clear()

        def fetch_fn(symbol, exchange, timeframe, lookback_days):
            return _candles([datetime.date.today().isoformat() + " 09:15:00"])

        loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=fetch_fn)
        assert len(read_calls) >= 1


class TestHealthGate:
    def test_future_timestamp_caught_for_synced_symbol(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))
        today = datetime.date.today().isoformat()
        loader.download_symbol(
            "RELIANCE",
            FakeGateway(_candles([f"{today} 09:15:00"])),
            years=1,
            timeframe="1m",
            exchange="NSE",
        )
        path = (
            tmp_path
            / "equities"
            / "candles"
            / "timeframe=1m"
            / "symbol=RELIANCE"
            / "data.parquet"
        )
        df = pd.read_parquet(path)
        future = pd.Timestamp(datetime.date.today() + datetime.timedelta(days=365))
        bad = pd.concat(
            [
                df,
                pd.DataFrame(
                    {
                        "timestamp": [future],
                        "symbol": ["RELIANCE"],
                        "exchange": ["NSE"],
                        "open": [100.0],
                        "high": [101.0],
                        "low": [99.0],
                        "close": [100.5],
                        "volume": [1000],
                        "oi": [0],
                    }
                ),
            ],
            ignore_index=True,
        )
        bad.to_parquet(path, index=False)

        tools = DatalakeTools(root=str(tmp_path))
        results = tools.health_check(timeframe="1m", min_rows=1, symbols=["RELIANCE"])
        assert results["future_timestamps"]["count"] >= 1
