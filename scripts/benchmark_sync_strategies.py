#!/usr/bin/env python3
"""Benchmark ad-hoc (single-broker) vs federated (quota-aware router) sync.

Fetches the *same* symbol list and date range through both strategies,
each into its own scratch datalake root (so neither run can silently
short-circuit into a cache-hit no-op via the other's merged Parquet
files) and reports wall-clock time + how many fetches hit a broker rate
limit (429 / "Too Many Requests" / DH-905).

Real network calls -- keep --limit modest (default 20).

Usage:
    python scripts/benchmark_sync_strategies.py [--timeframe 1d] [--limit 20] [--days 30] [--workers 5]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _connect import bootstrap_or_exit
from sync_datalake import ROOT, _build_federated_fetch_fn, _existing_symbols

from datalake.ingestion.loader import HistoricalDataLoader
from infrastructure.batch_executor import batch_execute

RATE_LIMIT_MARKERS = ("429", "too many requests", "dh-905", "rate limit")


def _is_rate_limited(err: str) -> bool:
    low = err.lower()
    return any(marker in low for marker in RATE_LIMIT_MARKERS)


def _run_strategy(
    name: str, symbols: list[str], timeframe: str, days: int, workers: int, sync_one
) -> dict:
    start = time.time()
    errors: dict[str, str] = {}

    def _on_error(entry: str, exc: Exception) -> None:
        errors[entry] = str(exc)

    results = batch_execute(symbols, sync_one, max_workers=workers, on_error=_on_error)
    elapsed = time.time() - start
    rate_limited = sum(1 for err in errors.values() if _is_rate_limited(err))
    return {
        "strategy": name,
        "elapsed_s": round(elapsed, 1),
        "symbols_ok": len(results),
        "symbols_errored": len(errors),
        "rate_limited_hits": rate_limited,
        "total_rows": sum(r.get("rows", 0) for r in results.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    symbols = _existing_symbols(ROOT, "equities", args.timeframe)[: args.limit]
    if not symbols:
        print(f"No existing equity symbols found at timeframe={args.timeframe} under {ROOT}")
        return 1
    print(
        f"Benchmarking {len(symbols)} symbols, timeframe={args.timeframe}, "
        f"days={args.days}, workers={args.workers}\n"
    )

    years = max(args.days / 365, 1 / 365)

    reports = []
    with tempfile.TemporaryDirectory() as adhoc_root, tempfile.TemporaryDirectory() as fed_root:
        print("Bootstrapping Dhan gateway for ad-hoc strategy...")
        dhan_gw = bootstrap_or_exit("dhan", load_instruments=True)
        adhoc_loader = HistoricalDataLoader(root=adhoc_root)

        def _adhoc_sync(symbol: str) -> dict:
            return adhoc_loader.download_symbol(
                symbol, dhan_gw, years=years, timeframe=args.timeframe, exchange="NSE"
            )

        reports.append(
            _run_strategy("ad-hoc", symbols, args.timeframe, args.days, args.workers, _adhoc_sync)
        )

        print("\nBootstrapping federated (Dhan + Upstox) strategy...")
        fetch_fn = _build_federated_fetch_fn()
        fed_loader = HistoricalDataLoader(root=fed_root)

        def _fed_sync(symbol: str) -> dict:
            return fed_loader.download_symbol(
                symbol, years=years, timeframe=args.timeframe, exchange="NSE", fetch_fn=fetch_fn
            )

        reports.append(
            _run_strategy("federated", symbols, args.timeframe, args.days, args.workers, _fed_sync)
        )

    print("\n" + "=" * 60)
    print(f"{'strategy':<12}{'time(s)':<10}{'ok':<6}{'errored':<10}{'429s':<8}{'rows':<8}")
    for r in reports:
        print(
            f"{r['strategy']:<12}{r['elapsed_s']:<10}{r['symbols_ok']:<6}"
            f"{r['symbols_errored']:<10}{r['rate_limited_hits']:<8}{r['total_rows']:<8}"
        )
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
