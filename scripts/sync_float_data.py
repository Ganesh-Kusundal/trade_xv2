#!/usr/bin/env python3
"""Sync float / shares-outstanding data for datalake symbols from yfinance.

Unlike candle data (scripts/sync_datalake.py), this doesn't need a broker
gateway -- yfinance's Ticker(...).info is a plain unauthenticated HTTP
lookup. Float/shares-outstanding only moves on corporate filings (quarterly
at most), so this is a manual/cron refresh, not part of the per-candle sync.

Usage:
    python scripts/sync_float_data.py [--workers 5] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
import yfinance as yf

from datalake.storage.catalog import DataCatalog
from infrastructure.batch_executor import batch_execute

ROOT = "data/lake"
OUT_PATH = Path("data/fundamentals/float_data.csv")

_FIELDS = {
    "floatShares": "float_shares",
    "sharesOutstanding": "shares_outstanding",
    "marketCap": "market_cap",
    "heldPercentInsiders": "held_pct_insiders",
    "heldPercentInstitutions": "held_pct_institutions",
}


def _fetch_one(symbol: str) -> dict:
    info = yf.Ticker(f"{symbol}.NS").info
    row = {"symbol": symbol}
    row.update({out_key: info.get(in_key) for in_key, out_key in _FIELDS.items()})
    row["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    catalog = DataCatalog(ROOT, read_only=True)
    symbols = catalog.list_symbols(timeframe="1m")
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"Syncing float data for {len(symbols)} symbols from yfinance...")

    errors: dict[str, str] = {}

    def _on_error(symbol: str, exc: Exception) -> None:
        errors[symbol] = str(exc)

    start = time.time()
    results = batch_execute(symbols, _fetch_one, max_workers=args.workers, on_error=_on_error)
    elapsed = time.time() - start

    rows = list(results.values())
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT_PATH, index=False)

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Symbols processed: {len(symbols)}")
    print(f"  Succeeded: {len(rows)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Written to: {OUT_PATH}")
    if errors:
        for sym, err in list(errors.items())[:20]:
            print(f"    {sym}: {err}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
