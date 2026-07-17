#!/usr/bin/env python3
"""Correct timezone-mislabeled candles in a date window by re-fetching
from Dhan and replacing the affected days outright -- combines the
delete+refetch repair into one pass per symbol instead of two separate
scripts, and pre-emptively rate-limits against Dhan's own declared
capability profile instead of reacting to HTTP 429s after the fact.

Why replace, not merge-dedupe: the corrupted rows and the correct rows
for the same trading day don't share exact timestamps for most of the
session (corrupted data is shifted -5:30h), but DO overlap for the
final ~45 minutes of the UTC-shifted block, which happens to fall
inside real session hours numerically (see progress-tracker.md). A
merge would only fix that overlap via dedupe-keep-last; explicitly
dropping every existing row for each corrected day and inserting the
fresh fetch is unambiguous and doesn't depend on that coincidence.

Rate limiting: Dhan's own declared capabilities
(brokers/dhan/config/capabilities.py) already encode the real limits
this script needs -- endpoint_class="historical" (sustained_rps=10,
burst=20) and historical_windows (max_chunk_days=90 for 1m) -- via the
canonical infrastructure.resilience.rate_limiter.create_rate_limiter().
That limiter is wired into Upstox's HTTP client already but not
Dhan's; rather than changing Dhan's client construction (used
everywhere, including live trading), this script acquires a token
before each gateway.history() call itself, so throttling is pre-emptive
without touching broker-wiring code.

Usage:
    python scripts/correct_tz_window.py --start 2025-07-01 --end 2026-06-14 [--workers 8]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
import pyarrow as pa

from _connect import bootstrap_or_exit

from brokers.dhan.config.capabilities import dhan_capabilities
from datalake.core.io import atomic_parquet_write
from datalake.core.paths import symbol_partition_path
from datalake.core.schema import enforce_canonical_schema
from datalake.ingestion.normalize import normalize_to_canonical
from datalake.quality.validation import validate_candles
from datalake.storage.catalog import DataCatalog
from infrastructure.batch_executor import batch_execute
from infrastructure.resilience.rate_limiter import create_rate_limiter

ROOT = "data/lake"


def _chunks(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    out = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--symbols-file", default=None, help="Only correct symbols listed (one per line)")
    args = parser.parse_args()

    window_start = date.fromisoformat(args.start)
    window_end = date.fromisoformat(args.end)

    caps = dhan_capabilities()
    window_constraint = caps.historical_window_for(args.timeframe)
    max_chunk_days = window_constraint.max_chunk_days if window_constraint else 90
    limiter = create_rate_limiter("dhan", caps=caps)

    catalog = DataCatalog(ROOT, read_only=True)
    symbols = catalog.list_symbols(timeframe=args.timeframe)
    if args.symbols_file:
        wanted = set(Path(args.symbols_file).read_text().split())
        symbols = [s for s in symbols if s in wanted]
    if args.limit:
        symbols = symbols[: args.limit]

    print(
        f"Correcting {len(symbols)} symbols, {args.start}..{args.end}, "
        f"chunk={max_chunk_days}d, rate-limited via Dhan's declared "
        f"'historical' profile"
    )

    gateway = bootstrap_or_exit("dhan", load_instruments=True)
    chunks = _chunks(window_start, window_end, max_chunk_days)
    errors: dict[str, str] = {}

    def _correct_one(symbol: str) -> int:
        path = symbol_partition_path(ROOT, symbol, args.timeframe)
        if not path.exists():
            return 0

        frames = []
        for chunk_start, chunk_end in chunks:
            limiter.acquire("historical", timeout=None)
            df = gateway.history(
                symbol,
                exchange="NSE",
                timeframe=args.timeframe,
                from_date=chunk_start.isoformat(),
                to_date=chunk_end.isoformat(),
            )
            if df is not None and not df.empty:
                frames.append(df)
        if not frames:
            return 0

        fresh = pd.concat(frames, ignore_index=True)
        fresh = normalize_to_canonical(fresh, symbol, "NSE")
        fresh = validate_candles(fresh, symbol=symbol, drop_invalid=True, timeframe=args.timeframe)
        if fresh.empty:
            return 0

        existing = pd.read_parquet(path)
        existing_ts = pd.to_datetime(existing["timestamp"])
        fresh_days = pd.to_datetime(fresh["timestamp"]).dt.date
        corrected_days = set(fresh_days.unique())
        keep = existing[~existing_ts.dt.date.isin(corrected_days)]

        merged = pd.concat([keep, fresh], ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
        merged = merged.sort_values("timestamp").reset_index(drop=True)

        table = pa.Table.from_pandas(merged, preserve_index=False)
        table = enforce_canonical_schema(table)
        atomic_parquet_write(path, table, compression="snappy")
        return len(fresh)

    def _on_error(symbol: str, exc: Exception) -> None:
        errors[symbol] = str(exc)

    start_t = time.time()
    results = batch_execute(symbols, _correct_one, max_workers=args.workers, on_error=_on_error)
    elapsed = time.time() - start_t

    total_rows = sum(results.values())
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Symbols processed: {len(results)}/{len(symbols)}")
    print(f"  Rows written: {total_rows}")
    print(f"  Errors: {len(errors)}")
    if errors:
        for sym, err in list(errors.items())[:20]:
            print(f"    {sym}: {err}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
