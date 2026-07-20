#!/usr/bin/env python3
"""Sync existing datalake symbols up to today.

Two fetch strategies:

--mode ad-hoc (single broker, no rate-limit intelligence)
    Auto-detects what's missing per symbol (repair_missing), fetches
    through a single gateway, chunked to respect that broker's
    max_chunk_days. No pre-emptive throttling and no cross-broker
    failover -- a burst of parallel workers can and does trip the
    broker's own rate limiter (HTTP 429), which just fails that symbol
    for this run.

--mode federated (default; both brokers, quota-aware)
    Routes every fetch through the existing application-layer smart
    router: MarketDataComposer.fetch_historical(), which federates
    across Dhan + Upstox concurrently through QuotaScheduler (per-broker
    token-bucket throttling -- pre-emptive, not react-after-429),
    chunk-plans per broker's real max_chunk_days/max_lookback_days, and
    merges results. See application/composer/factory.py:create_composers
    and domain/policies/defaults.py:default_source_selection_policy
    ("Historical: Quota-aware across Dhan + Upstox").

Both modes write through the same HistoricalDataLoader.repair_missing()
merge path (data/lake/**, hive-partitioned Parquet) -- only the fetch
strategy differs.

Usage:
    python scripts/sync_datalake.py [--mode federated|ad-hoc] [--timeframe 1m] [--workers 5] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _connect import bootstrap_or_exit, bootstrap_or_none

from datalake.ingestion.broker_selection import _TIMEFRAME_ALIASES
from datalake.ingestion.loader import HistoricalDataLoader
from datalake.storage.catalog import DataCatalog
from infrastructure.batch_executor import batch_execute

ROOT = "data/lake"


def _existing_symbols(root: str, asset: str, timeframe: str) -> list[str]:
    base = Path(root) / asset / "candles" / f"timeframe={timeframe}"
    if not base.exists():
        return []
    return sorted(
        p.name.removeprefix("symbol=")
        for p in base.iterdir()
        if p.is_dir() and p.name.startswith("symbol=")
    )


def _load_delisted(root: str) -> set[str]:
    """Symbols every broker has confirmed can't be fetched -- e.g. GSPL,
    JBCHEPHARM (both reject on Dhan *and* Upstox as of 2026-07-17). Skips
    them at the source instead of re-discovering the same broker rejection
    every run. Edit data/lake/delisted_symbols.csv to add/remove entries."""
    path = Path(root) / "delisted_symbols.csv"
    if not path.exists():
        return set()
    import csv

    with open(path) as f:
        return {row["symbol"] for row in csv.DictReader(f)}


def _build_federated_fetch_fn():
    """Wire the existing application-layer smart router (BrokerRouter +
    QuotaScheduler + HistoricalDataCoordinator) and adapt it to the
    narrow fetch_fn(symbol, exchange, timeframe, lookback_days) ->
    DataFrame shape HistoricalDataLoader expects.

    datalake/ doesn't import application/ (no existing precedent for
    that direction in this codebase -- see domain/policies/defaults.py
    for the routing policy, application/composer/factory.py for the
    composer wiring). This closure is the adapter boundary: it lives in
    a script, which is free to import from anywhere.
    """
    from application.composer.factory import create_composers
    from application.data.historical_coordinator import HistoricalQuery
    from domain.candles.historical import InstrumentRef
    from infrastructure.adapters.market_data_gateway_adapter import wrap_market_gateway
    from runtime.event_loop import run_coro_sync

    print("Bootstrapping Dhan gateway...")
    dhan_gw = bootstrap_or_exit("dhan", load_instruments=True)
    print("Bootstrapping Upstox gateway...")
    upstox_gw = bootstrap_or_none("upstox", env_path=Path(".env.upstox"), load_instruments=True)

    gateways = [wrap_market_gateway(dhan_gw, "dhan")]
    if upstox_gw is not None:
        gateways.append(wrap_market_gateway(upstox_gw, "upstox"))
    else:
        print("WARNING: Upstox unavailable, federating across Dhan only")

    composer, _execution = create_composers(gateways)

    def _fetch(symbol: str, exchange: str, timeframe: str, lookback_days: int):
        query = HistoricalQuery(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=_TIMEFRAME_ALIASES.get(timeframe, timeframe),
            from_date=date.today() - timedelta(days=lookback_days),
            to_date=date.today(),
        )
        series, ledger = run_coro_sync(composer.fetch_historical(query))
        if ledger.degraded:
            print(f"  [{symbol}] degraded: {ledger.degraded_reason}")
        return series.to_dataframe()

    return _fetch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ad-hoc", "federated"], default="federated")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    catalog = DataCatalog(ROOT)
    loader = HistoricalDataLoader(root=ROOT, catalog=catalog)

    fetch_fn = None
    gateway = None
    if args.mode == "federated":
        fetch_fn = _build_federated_fetch_fn()
    else:
        print("Bootstrapping Dhan gateway...")
        gateway = bootstrap_or_exit("dhan", load_instruments=True)

    equities = _existing_symbols(ROOT, "equities", args.timeframe)
    delisted = _load_delisted(ROOT)
    if delisted:
        skipped = [s for s in equities if s in delisted]
        if skipped:
            print(f"Skipping {len(skipped)} delisted symbol(s): {', '.join(skipped)}")
        equities = [s for s in equities if s not in delisted]
    symbols = [(s, "equities") for s in equities]
    if args.limit:
        symbols = symbols[: args.limit]

    print(
        f"Syncing {len(symbols)} equity symbols @ timeframe={args.timeframe}, "
        f"mode={args.mode}, workers={args.workers} "
        f"(indices synced separately -- different exchange code)"
    )

    start = time.time()
    results: dict[str, int] = {}
    errors: dict[str, str] = {}

    def _sync_one(entry: str) -> int:
        symbol, _asset = entry.split("|", 1)
        return loader.repair_missing(symbol, gateway, timeframe=args.timeframe, fetch_fn=fetch_fn)

    def _on_error(entry: str, exc: Exception) -> None:
        symbol, _ = entry.split("|", 1)
        errors[symbol] = str(exc)

    keys = [f"{s}|{a}" for s, a in symbols]
    raw_results = batch_execute(keys, _sync_one, max_workers=args.workers, on_error=_on_error)
    for k, rows in raw_results.items():
        symbol = k.split("|", 1)[0]
        results[symbol] = rows

    elapsed = time.time() - start
    total_new_rows = sum(results.values())
    synced_with_new_data = sum(1 for r in results.values() if r > 0)
    up_to_date = sum(1 for r in results.values() if r == 0)

    print(f"\nDone in {elapsed:.1f}s (mode={args.mode})")
    print(f"  Symbols processed: {len(results)}/{len(symbols)}")
    print(f"  Already up to date: {up_to_date}")
    print(f"  Received new data: {synced_with_new_data}")
    print(f"  Total new rows: {total_new_rows}")
    print(f"  Errors: {len(errors)}")
    if errors:
        for sym, err in list(errors.items())[:20]:
            print(f"    {sym}: {err}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
