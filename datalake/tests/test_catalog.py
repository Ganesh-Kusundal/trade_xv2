"""Tests for datalake.catalog — DuckDB metadata catalog."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from datalake.catalog import DataCatalog
from datalake.duckdb_utils import get_pool


def _close_writer(catalog: DataCatalog) -> None:
    """Close the RW connection so subsequent reads can open RO connections."""
    catalog.close()
    get_pool().close(catalog._db_path)


def _make_parquet(path: Path, n: int = 100, symbol: str = "TEST") -> None:
    """Create a synthetic canonical Parquet file."""
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=n, freq="1min")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": symbol,
            "exchange": "NSE",
            "open": close + np.random.randn(n) * 0.2,
            "high": close + np.abs(np.random.randn(n) * 0.5),
            "low": close - np.abs(np.random.randn(n) * 0.5),
            "close": close,
            "volume": np.random.randint(1000, 10000, n),
            "oi": np.zeros(n, dtype=np.int64),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


class TestDataCatalogInit:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        _ = catalog.conn
        assert (tmp_path / "catalog.duckdb").exists()
        catalog.close()

    def test_initializes_schema(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        _ = catalog.conn
        tables = catalog.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "symbols" in table_names
        assert "data_quality" in table_names
        assert "download_jobs" in table_names
        catalog.close()

    def test_read_only_mode_queries_existing_db(self, tmp_path: Path) -> None:
        # Create the DB with a writer first.
        writer = DataCatalog(root=str(tmp_path))
        writer.register_symbol("RELIANCE", total_rows=100)
        _close_writer(writer)

        # Re-open in read-only mode and query.
        reader = DataCatalog(root=str(tmp_path), read_only=True)
        result = reader.get_symbol("RELIANCE")
        assert result is not None
        assert result["total_rows"] == 100
        reader.close()

    def test_read_only_mode_rejects_writes(self, tmp_path: Path) -> None:
        writer = DataCatalog(root=str(tmp_path))
        writer.register_symbol("RELIANCE", total_rows=100)
        writer.close()

        reader = DataCatalog(root=str(tmp_path), read_only=True)
        with pytest.raises(duckdb.InvalidInputException):
            reader.register_symbol("TCS", total_rows=100)
        reader.close()


class TestDataCatalogSymbols:
    def test_register_and_get(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.register_symbol(
            "RELIANCE",
            exchange="NSE",
            first_date=date(2020, 1, 1),
            last_date=date(2026, 6, 10),
            total_rows=463000,
        )
        _close_writer(catalog)
        result = catalog.get_symbol("RELIANCE")
        assert result is not None
        assert result["symbol"] == "RELIANCE"
        assert result["exchange"] == "NSE"
        assert result["total_rows"] == 463000

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        _close_writer(catalog)
        result = catalog.get_symbol("NONEXISTENT")
        assert result is None

    def test_register_overwrites(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.register_symbol("TEST", total_rows=100)
        catalog.register_symbol("TEST", total_rows=200)
        _close_writer(catalog)
        result = catalog.get_symbol("TEST")
        assert result["total_rows"] == 200

    def test_list_symbols(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.register_symbol("AAA")
        catalog.register_symbol("BBB")
        catalog.register_symbol("CCC")
        _close_writer(catalog)
        symbols = catalog.list_symbols()
        assert symbols == ["AAA", "BBB", "CCC"]

    def test_list_symbols_by_timeframe(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.register_symbol("TEST", timeframe="1m")
        catalog.register_symbol("TEST2", timeframe="5m")
        _close_writer(catalog)
        symbols_1m = catalog.list_symbols(timeframe="1m")
        symbols_5m = catalog.list_symbols(timeframe="5m")
        assert "TEST" in symbols_1m
        assert "TEST2" in symbols_5m
        assert "TEST2" not in symbols_1m

    def test_get_parquet_path(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        parquet_path = tmp_path / "data.parquet"
        catalog.register_symbol("TEST", parquet_path=str(parquet_path))
        _close_writer(catalog)
        result = catalog.get_parquet_path("TEST")
        assert result == parquet_path

    def test_get_parquet_path_nonexistent(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        _close_writer(catalog)
        result = catalog.get_parquet_path("NONEXISTENT")
        assert result is None


class TestDataCatalogQuality:
    def test_record_and_query(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.record_quality(
            "RELIANCE",
            total_rows=463000,
            missing_candles=5,
            duplicate_candles=0,
            gap_days=2,
            min_date=date(2020, 1, 1),
            max_date=date(2026, 6, 10),
            completeness_pct=98.5,
            status="OK",
        )
        result = catalog.conn.execute(
            "SELECT * FROM data_quality WHERE symbol = 'RELIANCE'"
        ).fetchone()
        assert result is not None
        catalog.close()

    def test_record_overwrites(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.record_quality("TEST", total_rows=100, status="OK")
        catalog.record_quality("TEST", total_rows=200, status="WARNING")
        count = catalog.conn.execute(
            "SELECT COUNT(*) FROM data_quality WHERE symbol = 'TEST'"
        ).fetchone()[0]
        assert count == 1
        catalog.close()


class TestDataCatalogSummary:
    def test_summary(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        catalog.register_symbol("AAA", total_rows=100)
        catalog.register_symbol("BBB", total_rows=200)
        _close_writer(catalog)
        summary = catalog.summary()
        assert summary["symbols"] == 2
        assert summary["total_rows"] == 300
        assert summary["quality_records"] == 0

    def test_summary_empty(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        _close_writer(catalog)
        summary = catalog.summary()
        assert summary["symbols"] == 0
        assert summary["total_rows"] == 0


class TestDataCatalogScanParquet:
    def test_scan_parquet_files(self, tmp_path: Path) -> None:
        # Create hive directory structure
        candles_dir = tmp_path / "equities" / "candles" / "timeframe=1m"
        for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
            _make_parquet(candles_dir / f"symbol={sym}" / "data.parquet", symbol=sym)

        catalog = DataCatalog(root=str(tmp_path))
        count = catalog.scan_parquet_files()

        assert count == 3
        _close_writer(catalog)
        symbols = catalog.list_symbols()
        assert "HDFCBANK" in symbols
        assert "RELIANCE" in symbols
        assert "TCS" in symbols

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        catalog = DataCatalog(root=str(tmp_path))
        count = catalog.scan_parquet_files()
        assert count == 0
        catalog.close()


class TestDataCatalogThreadSafety:
    def test_concurrent_register_symbol(self, tmp_path: Path) -> None:
        import threading

        catalog = DataCatalog(root=str(tmp_path))
        errors: list[Exception] = []

        def register(i: int) -> None:
            try:
                catalog.register_symbol(
                    symbol=f"SYM{i:03d}",
                    exchange="NSE",
                    first_date=date(2026, 1, 1),
                    last_date=date(2026, 1, 31),
                    total_rows=i,
                    timeframe="1m",
                    parquet_path=f"path/{i}",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        _close_writer(catalog)
        symbols = catalog.list_symbols()
        assert len(symbols) == 20
