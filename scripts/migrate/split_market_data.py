#!/usr/bin/env python3
"""Migrate market_data/ → data/lake/ + data/state/.

Phase D-Phase2 of the E2E spec (doc 12 §7). Separates three concerns
that the old market_data/ directory conflated:

  lake  = Parquet OHLCV / options / indices (large, append-heavy)
  state = OMS SQLite, execution ledger, event log, research cache

Run from the repo root:
    python scripts/migrate/split_market_data.py [--dry-run]

After running, update DataPaths defaults in domain/ports/data_catalog.py
to point at data/lake and data/state.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# ── Source → destination mapping ──────────────────────────────────────

# Files that move to data/lake/
LAKE_MOVES: list[tuple[str, str]] = [
    ("market_data/catalog.duckdb", "data/lake/catalog.duckdb"),
    ("market_data/equities", "data/lake/equities"),
    ("market_data/indices", "data/lake/indices"),
    ("market_data/options", "data/lake/options"),
    ("market_data/curated", "data/lake/curated"),
    ("market_data/materialized", "data/lake/materialized"),
    ("market_data/features", "data/lake/features"),
]

# Files that move to data/state/
STATE_MOVES: list[tuple[str, str]] = [
    ("market_data/oms_orders.sqlite", "data/state/oms/orders.sqlite"),
    ("market_data/execution_ledger.sqlite", "data/state/oms/execution_ledger.sqlite"),
    ("market_data/events", "data/state/events"),
    ("market_data/live_snapshot.json", "data/state/live_snapshot.json"),
    ("market_data/backtest_results.sqlite", "data/state/research/backtest_results.sqlite"),
    ("market_data/journal.sqlite", "data/state/research/journal.sqlite"),
]


def _move(src: str, dst: str, *, dry_run: bool) -> None:
    """Move a file or directory, creating parents as needed."""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        print(f"  SKIP  {src} (not found)")
        return

    if dst_path.exists():
        print(f"  SKIP  {dst} (already exists)")
        return

    if dry_run:
        print(f"  MOVE  {src} → {dst}")
        return

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_path), str(dst_path))
    print(f"  DONE  {src} → {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split market_data/ into lake + state")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be moved")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.dry_run and not args.force:
        confirm = input(
            "This will move files from market_data/ to data/lake/ + data/state/. Continue? [y/N] "
        )
        if confirm.lower() != "y":
            print("Aborted.")
            sys.exit(1)

    print("\n=== Lake moves ===")
    for src, dst in LAKE_MOVES:
        _move(src, dst, dry_run=args.dry_run)

    print("\n=== State moves ===")
    for src, dst in STATE_MOVES:
        _move(src, dst, dry_run=args.dry_run)

    print("\nDone. Next steps:")
    print("  1. Update DataPaths defaults in domain/ports/data_catalog.py")
    print("  2. Run tests: pytest tests/ -x")
    print("  3. Remove market_data/ after verifying (or leave as compat symlink)")


if __name__ == "__main__":
    main()
