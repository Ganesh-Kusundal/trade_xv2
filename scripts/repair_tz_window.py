#!/usr/bin/env python3
"""Delete timezone-mislabeled candles (the Dhan/Upstox -5:30h shift bug,
fixed in brokers/dhan/data/historical.py and domain/candles/historical.py)
in a given date window, per symbol.

This is the delete half of the repair -- run scripts/sync_datalake.py
--mode ad-hoc afterward to backfill the window cleanly (the fix means
newly-fetched data will land correctly; the validate_candles() session-
hours guard also now rejects any bad candle before it's ever written).

Usage:
    python scripts/repair_tz_window.py --start 2025-07-01 --end 2026-06-14
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.core.paths import symbol_partition_path
from datalake.core.schema import enforce_canonical_schema
from datalake.storage.catalog import DataCatalog

ROOT = "data/lake"
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DD, inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD, inclusive")
    parser.add_argument("--timeframe", default="1m")
    args = parser.parse_args()

    window_start = date.fromisoformat(args.start)
    window_end = date.fromisoformat(args.end)

    catalog = DataCatalog(ROOT, read_only=True)
    symbols = catalog.list_symbols(timeframe=args.timeframe)

    total_dropped = 0
    symbols_touched = 0
    for symbol in symbols:
        path = symbol_partition_path(ROOT, symbol, args.timeframe)
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if df.empty:
            continue
        ts = pd.to_datetime(df["timestamp"])
        d = ts.dt.date
        t = ts.dt.time
        in_window = (d >= window_start) & (d <= window_end)
        corrupted = in_window & ((t < SESSION_OPEN) | (t > SESSION_CLOSE))
        n = int(corrupted.sum())
        if n == 0:
            continue
        clean = df[~corrupted].copy()
        table = pa.Table.from_pandas(clean, preserve_index=False)
        table = enforce_canonical_schema(table)
        atomic_parquet_write(path, table, compression="snappy")
        total_dropped += n
        symbols_touched += 1
        print(f"{symbol}: dropped {n} corrupted rows ({len(df)} -> {len(clean)})")

    print(f"\nDone. Symbols touched: {symbols_touched}, rows dropped: {total_dropped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
