"""Regression: API epoch filters are naive UTC; lake timestamps are naive IST."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.gateway import DataLakeGateway


def _write_ist_bar(tmp_path: Path, symbol: str = "RELIANCE", ist_time: str = "2026-01-15 09:15:00") -> None:
    hive = tmp_path / "equities" / "candles" / "timeframe=1m" / f"symbol={symbol}"
    hive.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp(ist_time)],
            "symbol": [symbol],
            "exchange": ["NSE"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "oi": [0],
        }
    )
    table = pa.Table.from_pandas(df, preserve_index=False)
    atomic_parquet_write(hive / "data.parquet", table, compression="snappy")


def test_query_candles_converts_utc_from_ts_to_ist_naive(tmp_path: Path) -> None:
    """5h30m regression: UTC 03:45 filter must match IST 09:15 lake bar."""
    _write_ist_bar(tmp_path)
    gw = DataLakeGateway(root=str(tmp_path))

    # Same instant as 09:15 IST, expressed as naive UTC wall clock from epoch ms.
    from_ts = pd.Timestamp("2026-01-15 03:45:00")

    result = gw.query_candles("RELIANCE", "1m", from_ts=from_ts)

    assert result is not None
    assert len(result) == 1
    assert result["timestamp"].iloc[0] == pd.Timestamp("2026-01-15 09:15:00")


def test_query_candles_converts_utc_to_ts_to_ist_naive(tmp_path: Path) -> None:
    hive = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=RELIANCE"
    hive.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2026-01-15 09:15:00"),
                pd.Timestamp("2026-01-15 09:16:00"),
            ],
            "symbol": ["RELIANCE", "RELIANCE"],
            "exchange": ["NSE", "NSE"],
            "open": [100.0, 100.5],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.0],
            "volume": [1000, 1100],
            "oi": [0, 0],
        }
    )
    import pyarrow as pa

    from datalake.core.io import atomic_parquet_write

    table = pa.Table.from_pandas(df, preserve_index=False)
    atomic_parquet_write(hive / "data.parquet", table, compression="snappy")
    gw = DataLakeGateway(root=str(tmp_path))

    # Upper bound: UTC 03:46 == IST 09:16
    to_ts = pd.Timestamp("2026-01-15 03:46:00")

    result = gw.query_candles("RELIANCE", "1m", to_ts=to_ts)

    assert result is not None
    assert len(result) == 2
    assert list(result["timestamp"]) == [
        pd.Timestamp("2026-01-15 09:15:00"),
        pd.Timestamp("2026-01-15 09:16:00"),
    ]


def test_query_candles_without_conversion_would_miss_bar(tmp_path: Path) -> None:
    """Document the pre-fix failure mode: naive UTC 03:45 < naive IST 09:15."""
    _write_ist_bar(tmp_path)
    gw = DataLakeGateway(root=str(tmp_path))

    from_ts = pd.Timestamp("2026-01-15 03:45:00")
    lake_ts = pd.Timestamp("2026-01-15 09:15:00")

    assert from_ts < lake_ts  # raw compare wrongly excludes the bar

    result = gw.query_candles("RELIANCE", "1m", from_ts=from_ts)
    assert result is not None and len(result) == 1
