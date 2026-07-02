"""Benchmarks for API candle data endpoint latency.

Measures the time to serve candle data through the DuckDB
predicate-pushdown path (Phase 3.2) vs full Parquet scan.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pytest

from datalake.core.io import atomic_parquet_write


@pytest.fixture(scope="module")
def candle_db(tmp_path_factory: pytest.TempPathFactory) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with test candle data."""
    root = tmp_path_factory.mktemp("bench_api")
    candles_dir = root / "curated" / "equities" / "candles" / "year=2024" / "month=01"
    candles_dir.mkdir(parents=True)

    n = 20_000
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-02 09:15", periods=n, freq="1min"),
        "symbol": "TESTSYM",
        "open": [100.0 + (i % 375) * 0.01 for i in range(n)],
        "high": [101.0 + (i % 375) * 0.01 for i in range(n)],
        "low": [99.0 + (i % 375) * 0.01 for i in range(n)],
        "close": [100.5 + (i % 375) * 0.01 for i in range(n)],
        "volume": [1000 + i for i in range(n)],
    })
    atomic_parquet_write(candles_dir / "data_000.parquet", pa.Table.from_pandas(df))

    conn = duckdb.connect(":memory:")
    pattern = str(root / "curated" / "equities" / "candles" / "year=*" / "month=*" / "data_*.parquet")
    conn.execute(f"""
        CREATE VIEW v_candles AS
        SELECT * FROM read_parquet('{pattern}', hive_partitioning=true)
    """)
    return conn


class TestAPICandleBenchmarks:
    """Benchmark API-style candle queries."""

    def test_recent_candles_with_pushdown(
        self, benchmark, candle_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Simulate the optimized API endpoint query (predicate + projection pushdown)."""
        benchmark(
            candle_db.execute,
            """SELECT timestamp, open, high, low, close, volume
               FROM v_candles
               WHERE symbol = 'TESTSYM'
                 AND timestamp >= '2024-01-10'
                 AND timestamp <= '2024-01-15'
               ORDER BY timestamp DESC
               LIMIT 100""",
        )

    def test_last_n_candles(self, benchmark, candle_db: duckdb.DuckDBPyConnection) -> None:
        """Simulate fetching the last N candles for a symbol."""
        benchmark(
            candle_db.execute,
            """SELECT timestamp, open, high, low, close, volume
               FROM v_candles
               WHERE symbol = 'TESTSYM'
               ORDER BY timestamp DESC
               LIMIT 375""",
        )

    def test_ohlc_aggregation(self, benchmark, candle_db: duckdb.DuckDBPyConnection) -> None:
        """Simulate daily OHLCV aggregation from 1m candles."""
        benchmark(
            candle_db.execute,
            """SELECT CAST(timestamp AS DATE) as dt,
                      FIRST(open) as day_open,
                      MAX(high) as day_high,
                      MIN(low) as day_low,
                      LAST(close) as day_close,
                      SUM(volume) as day_volume
               FROM v_candles
               WHERE symbol = 'TESTSYM'
               GROUP BY CAST(timestamp AS DATE)
               ORDER BY dt""",
        )
