#!/usr/bin/env python3
"""CLI entrypoint for runtime.datalake_sync — federated datalake self-update.

See ``runtime.datalake_sync`` and ``datalake.ingestion.auto_sync`` for the
sync loop; this script only parses CLI arguments.

Usage:
    # Daily catch-up (default): tail gaps only, ~15 min for full lake
    python scripts/sync_datalake.py

    # First-time / regenerate allowlist from on-disk parquets (excludes BSE100/200/500)
    python scripts/bootstrap_sync_manifest.py --overwrite --purge-excluded

    # Slow mid-history hole repair — run off-hours, not every day
    python scripts/sync_datalake.py --repair-gaps

    # Both phases (original behaviour)
    python scripts/sync_datalake.py --full
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _connect import bootstrap_or_exit

ROOT = "data/lake"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ad-hoc", "federated"], default="federated")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip post-sync corruption scan (dev/ad-hoc only)",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--tail-only",
        action="store_const",
        const="tail",
        dest="repair_scope",
        help="Catch up last bar through today only (default, fast daily sync)",
    )
    scope.add_argument(
        "--repair-gaps",
        action="store_const",
        const="internal",
        dest="repair_scope",
        help="Fill mid-history trading-day holes only (slow — run off-hours)",
    )
    scope.add_argument(
        "--full",
        action="store_const",
        const="all",
        dest="repair_scope",
        help="Tail + internal gap repair (slowest)",
    )
    parser.set_defaults(repair_scope="tail")
    parser.add_argument(
        "--with-options",
        action="store_true",
        help="After equity/index sync, run federated options sync (NIFTY/BANKNIFTY)",
    )
    args = parser.parse_args()

    from runtime import datalake_sync

    sync_kwargs = dict(
        root=ROOT,
        timeframe=args.timeframe,
        workers=args.workers,
        limit=args.limit,
        run_health_check=not args.skip_health_check,
        repair_scope=args.repair_scope,
    )

    if args.mode == "federated":
        report = datalake_sync.run_federated_sync(**sync_kwargs)
    else:
        print(
            "WARNING: ad-hoc mode skips quota management and federated degraded-data "
            "gating — not for production use.",
            file=sys.stderr,
        )
        print("Bootstrapping Dhan gateway...")
        gateway = bootstrap_or_exit("dhan", load_instruments=True)
        report = datalake_sync.run_adhoc_sync(gateway=gateway, **sync_kwargs)

    scope_label = {"tail": "tail-only", "internal": "repair-gaps", "all": "full"}[
        args.repair_scope
    ]
    print(
        f"\nSyncing equities + indices @ timeframe={args.timeframe}, "
        f"mode={args.mode}, scope={scope_label}, workers={args.workers}"
    )
    print(f"\nDone in {report.elapsed_s:.1f}s (mode={args.mode})")
    print(f"  Symbols processed: {len(report.results)}/{report.symbols_total}")
    print(f"  Already up to date: {report.up_to_date}")
    print(f"  Received new data: {report.synced_with_new_data}")
    print(f"  Total new rows: {report.total_new_rows}")
    print(f"  Errors: {len(report.errors)}")
    if report.errors:
        for sym, err in list(report.errors.items())[:20]:
            print(f"    {sym}: {err}")

    if not args.skip_health_check and report.health_results:
        print("\nPost-sync health check...")
        if report.health_ok:
            print("  ALL CHECKS PASSED")
        else:
            print("  ISSUES FOUND")
            for name, result in report.health_results.items():
                if name == "thin_coverage":
                    n = len(result.get("sample", []))
                    if n:
                        print(
                            f"  FAIL thin_coverage: {n} symbol(s) below "
                            f"{result['min_rows_threshold']} rows"
                        )
                        for row in result["sample"][:5]:
                            print(f"    {row}")
                    continue
                count = result.get("count", 0)
                if count:
                    print(f"  FAIL {name}: {count} row(s)")
                    for row in result.get("sample", [])[:5]:
                        print(f"    {row}")

    if not report.ok:
        return 1
    if args.with_options:
        return _run_options_sync()
    return 0


def _run_options_sync() -> int:
    from runtime.options_sync import run_federated_options_sync

    print("\nOptions sync (Dhan federation)...")
    summary = run_federated_options_sync(print_fn=print)
    print(
        f"  Options: {summary['files_created']} created, "
        f"{summary['files_merged']} merged, {summary['new_rows']:,} new rows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
