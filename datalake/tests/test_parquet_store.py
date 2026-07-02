"""Unit tests for :class:`datalake.store.parquet_store.ParquetStore`."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.storage.parquet_store import ParquetStore


def _make_dataframe(symbol: str, n: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01 09:15", periods=n, freq="1min"),
            "symbol": symbol,
            "exchange": "NSE",
            "open": [100.0 + i * 0.1 for i in range(n)],
            "high": [101.0 + i * 0.1 for i in range(n)],
            "low": [99.0 + i * 0.1 for i in range(n)],
            "close": [100.5 + i * 0.1 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )


def _write_symbol(root: Path, symbol: str, timeframe: str = "1m", n: int = 60) -> Path:
    hive = root / "equities" / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}"
    hive.mkdir(parents=True, exist_ok=True)
    path = hive / "data.parquet"
    table = pa.Table.from_pandas(_make_dataframe(symbol, n=n), preserve_index=False)
    atomic_parquet_write(path, table, compression="snappy")
    return path


def test_load_candles_reads_native_timeframe(tmp_path: Path) -> None:
    _write_symbol(tmp_path, "RELIANCE", timeframe="1m", n=10)
    store = ParquetStore(root=str(tmp_path))

    df = store.load_candles("RELIANCE", "1m")

    assert df is not None
    assert len(df) == 10
    assert df["symbol"].iloc[0] == "RELIANCE"


def test_load_candles_resamples_from_one_minute(tmp_path: Path) -> None:
    _write_symbol(tmp_path, "TCS", timeframe="1m", n=60)
    store = ParquetStore(root=str(tmp_path))

    df = store.load_candles("TCS", "5m")

    assert df is not None
    assert len(df) < 60
    assert "close" in df.columns
    assert "timestamp" in df.columns


def test_resample_uses_cache(tmp_path: Path) -> None:
    _write_symbol(tmp_path, "INFY", timeframe="1m", n=30)
    store = ParquetStore(root=str(tmp_path))
    df_1m = store.load_candles("INFY", "1m")
    assert df_1m is not None

    first = store.resample(df_1m, "5m")
    second = store.resample(df_1m, "5m")

    assert len(first) == len(second)
    pd.testing.assert_frame_equal(first, second)


def test_load_candles_missing_symbol_returns_none(tmp_path: Path) -> None:
    store = ParquetStore(root=str(tmp_path))
    assert store.load_candles("MISSING", "1m") is None


def test_list_symbols_discovers_hive_partitions(tmp_path: Path) -> None:
    _write_symbol(tmp_path, "RELIANCE")
    _write_symbol(tmp_path, "TCS")
    store = ParquetStore(root=str(tmp_path))

    symbols = store.list_symbols("1m")

    assert symbols == ["RELIANCE", "TCS"]


def test_parquet_path_matches_hive_layout(tmp_path: Path) -> None:
    store = ParquetStore(root=str(tmp_path))
    path = store.parquet_path("RELIANCE", "1m")
    assert (
        path
        == tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=RELIANCE" / "data.parquet"
    )
