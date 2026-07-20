"""Benchmarks for DuckDB query latency.

Measures the time to execute common analytical queries against
Parquet-backed DuckDB views.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pytest

from datalake.core.io import atomic_parquet_write


@pytest.fixture(scope="module")
def populated_lake(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a small curated parquet layout for benchmarking."""
    root = tmp_path_factory.mktemp("bench_duckdb")
    candles_dir = root / "curated" / "equities" / "candles" / "year=2024" / "month=01"
    candles_dir.mkdir(parents=True)

    n = 10_000
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-02 09:15", periods=n, freq="1min"),
            "symbol": "TESTSYM",
            "open": [100.0 + i * 0.01 for i in range(n)],
            "high": [101.0 + i * 0.01 for i in range(n)],
            "low": [99.0 + i * 0.01 for i in range(n)],
            "close": [100.5 + i * 0.01 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )
    atomic_parquet_write(candles_dir / "data_000.parquet", pa.Table.from_pandas(df))
    return root


@pytest.fixture(scope="module")
def duck_conn(populated_lake: Path) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    pattern = str(
        populated_lake
        / "curated"
        / "equities"
        / "candles"
        / "year=*"
        / "month=*"
        / "data_*.parquet"
    )
    conn.execute(f"""
        CREATE VIEW v_candles AS
        SELECT * FROM read_parquet('{pattern}', hive_partitioning=true)
    """)
    return conn


class TestDuckDBQueryBenchmarks:
    """Benchmark common DuckDB query patterns."""

    def test_simple_select_all(self, benchmark, duck_conn: duckdb.DuckDBPyConnection) -> None:
        benchmark(duck_conn.execute, "SELECT * FROM v_candles")

    def test_filtered_query(self, benchmark, duck_conn: duckdb.DuckDBPyConnection) -> None:
        benchmark(
            duck_conn.execute,
            "SELECT * FROM v_candles WHERE symbol = 'TESTSYM' AND close > 150.0",
        )

    def test_aggregation_query(self, benchmark, duck_conn: duckdb.DuckDBPyConnection) -> None:
        benchmark(
            duck_conn.execute,
            """SELECT symbol, AVG(close), SUM(volume), COUNT(*)
               FROM v_candles GROUP BY symbol""",
        )

    def test_window_function_query(self, benchmark, duck_conn: duckdb.DuckDBPyConnection) -> None:
        benchmark(
            duck_conn.execute,
            """SELECT timestamp, close,
                      AVG(close) OVER (ORDER BY timestamp ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma20
               FROM v_candles""",
        )

    def test_limit_query(self, benchmark, duck_conn: duckdb.DuckDBPyConnection) -> None:
        benchmark(
            duck_conn.execute,
            "SELECT * FROM v_candles ORDER BY timestamp DESC LIMIT 10",
        )
