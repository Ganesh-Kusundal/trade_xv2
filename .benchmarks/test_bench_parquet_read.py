"""Benchmarks for Parquet read latency.

Measures the time to read Parquet files using various strategies:
full scan, predicate pushdown via DuckDB, and PyArrow direct read.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from datalake.core.io import atomic_parquet_write


@pytest.fixture(scope="module")
def parquet_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a test parquet file with realistic candle data."""
    path = tmp_path_factory.mktemp("bench_parquet") / "candles.parquet"
    n = 50_000
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-02 09:15", periods=n, freq="1min"),
            "symbol": "TESTSYM",
            "open": [100.0 + (i % 375) * 0.01 for i in range(n)],
            "high": [101.0 + (i % 375) * 0.01 for i in range(n)],
            "low": [99.0 + (i % 375) * 0.01 for i in range(n)],
            "close": [100.5 + (i % 375) * 0.01 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )
    atomic_parquet_write(path, pa.Table.from_pandas(df))
    return path


class TestParquetReadBenchmarks:
    """Benchmark different Parquet read strategies."""

    def test_pandas_read_parquet_full(self, benchmark, parquet_file: Path) -> None:
        benchmark(pd.read_parquet, parquet_file)

    def test_pyarrow_read_table_full(self, benchmark, parquet_file: Path) -> None:
        benchmark(pq.read_table, parquet_file)

    def test_pyarrow_read_with_columns(self, benchmark, parquet_file: Path) -> None:
        benchmark(pq.read_table, parquet_file, columns=["timestamp", "close", "volume"])

    def test_pyarrow_read_with_filter(self, benchmark, parquet_file: Path) -> None:
        benchmark(
            pq.read_table,
            parquet_file,
            columns=["timestamp", "close"],
            filters=[("close", ">", 110.0)],
        )
