"""Tests for the data health check."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from datalake.health_check import run_health_check
from datalake.io import atomic_parquet_write


def _make_valid_data(path: Path) -> None:
    """Create a valid 1m candle Parquet file with IST timestamps."""
    n = 100
    dates = pd.date_range("2026-06-01 09:15", periods=n, freq="1min")
    df = pd.DataFrame({
        "timestamp": dates,
        "symbol": "TEST",
        "exchange": "NSE",
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
        "volume": [1000] * n,
        "oi": [0] * n,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    atomic_parquet_write(path, table, compression="snappy")


def _init_catalog(db_path: Path) -> None:
    """Initialize a DuckDB catalog with the symbols and quality tables."""
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            symbol VARCHAR PRIMARY KEY,
            exchange VARCHAR DEFAULT 'NSE'
        )
    """)
    conn.close()


def _create_view(db_path: Path, data_root: Path) -> None:
    """Create the v_candles_1m view pointing to a hive directory."""
    conn = duckdb.connect(str(db_path))
    conn.execute(f"""
        CREATE OR REPLACE VIEW v_candles_1m AS
        SELECT * FROM read_parquet('{data_root}/symbol=*/data.parquet')
    """)
    conn.close()


class TestHealthCheckMissingDB:
    def test_missing_db_returns_error(self, tmp_path: Path) -> None:
        result = run_health_check(str(tmp_path / "nonexistent.duckdb"))
        assert result == 1


class TestHealthCheckClean:
    def test_clean_data_passes(self, tmp_path: Path) -> None:
        # Create hive structure
        root = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"
        _make_valid_data(root / "symbol=TEST" / "data.parquet")

        db_path = tmp_path / "catalog.duckdb"
        _init_catalog(db_path)
        _create_view(db_path, root)

        result = run_health_check(str(db_path), min_rows=50)
        assert result == 0


class TestHealthCheckDuplicates:
    def test_duplicate_timestamps_detected(self, tmp_path: Path) -> None:
        root = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"
        # Create data with a duplicate timestamp
        dates = list(pd.date_range("2026-06-01 09:15", periods=50, freq="1min"))
        dates.append(dates[0])  # duplicate
        df = pd.DataFrame({
            "timestamp": dates,
            "symbol": "TEST",
            "exchange": "NSE",
            "open": [100.0] * len(dates),
            "high": [101.0] * len(dates),
            "low": [99.0] * len(dates),
            "close": [100.5] * len(dates),
            "volume": [1000] * len(dates),
            "oi": [0] * len(dates),
        })
        path = root / "symbol=TEST" / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(path, table, compression="snappy")

        db_path = tmp_path / "catalog.duckdb"
        _init_catalog(db_path)
        _create_view(db_path, root)

        result = run_health_check(str(db_path))
        assert result == 1


class TestHealthCheckMarketHours:
    def test_outside_market_hours_detected(self, tmp_path: Path) -> None:
        root = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"
        # Create data with timestamps outside 9:15-15:30
        df = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2026-06-01 08:00",  # before market
                "2026-06-01 16:00",  # after market
            ]),
            "symbol": "TEST",
            "exchange": "NSE",
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 99.0],
            "close": [100.5, 100.5],
            "volume": [1000, 1000],
            "oi": [0, 0],
        })
        path = root / "symbol=TEST" / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(path, table, compression="snappy")

        db_path = tmp_path / "catalog.duckdb"
        _init_catalog(db_path)
        _create_view(db_path, root)

        result = run_health_check(str(db_path))
        assert result == 1


class TestHealthCheckOHLCV:
    def test_high_less_than_low_detected(self, tmp_path: Path) -> None:
        root = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-06-01 09:15", "2026-06-01 09:16"]),
            "symbol": ["TEST", "TEST"],
            "exchange": ["NSE", "NSE"],
            "open": [100.0, 100.0],
            "high": [99.0, 101.0],   # high < low on row 1
            "low": [101.0, 99.0],    # low > high on row 1
            "close": [100.5, 100.5],
            "volume": [1000, 1000],
            "oi": [0, 0],
        })
        path = root / "symbol=TEST" / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(path, table, compression="snappy")

        db_path = tmp_path / "catalog.duckdb"
        _init_catalog(db_path)
        _create_view(db_path, root)

        result = run_health_check(str(db_path))
        assert result == 1


class TestHealthCheckSymbolNormalization:
    def test_lowercase_symbol_detected(self, tmp_path: Path) -> None:
        root = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-06-01 09:15"]),
            "symbol": ["reliance"],  # lowercase
            "exchange": ["NSE"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "oi": [0],
        })
        path = root / "symbol=reliance" / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(path, table, compression="snappy")

        db_path = tmp_path / "catalog.duckdb"
        _init_catalog(db_path)
        _create_view(db_path, root)

        result = run_health_check(str(db_path))
        assert result == 1

    def test_eq_suffix_detected(self, tmp_path: Path) -> None:
        root = tmp_path / "market_data" / "equities" / "candles" / "timeframe=1m"
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-06-01 09:15"]),
            "symbol": ["RELIANCE-EQ"],
            "exchange": ["NSE"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "oi": [0],
        })
        path = root / "symbol=RELIANCE-EQ" / "data.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(path, table, compression="snappy")

        db_path = tmp_path / "catalog.duckdb"
        _init_catalog(db_path)
        _create_view(db_path, root)

        result = run_health_check(str(db_path))
        assert result == 1
