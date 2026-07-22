#!/usr/bin/env python3
"""One-time bootstrap of data/lake/sync_manifest.csv from on-disk parquet dirs.

Excludes orphan BSE100/200/500 indices by default. Re-run with --overwrite to
regenerate after manual manifest edits are lost.

Usage:
    python scripts/bootstrap_sync_manifest.py
    python scripts/bootstrap_sync_manifest.py --overwrite
    python scripts/bootstrap_sync_manifest.py --purge-excluded
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = "data/lake"
DEFAULT_EXCLUDE = ("BSE100", "BSE200", "BSE500")


def _purge_excluded(root: str, symbols: tuple[str, ...]) -> None:
    from datalake.storage.catalog import DataCatalog

    catalog = DataCatalog(root)
    for sym in symbols:
        parquet = (
            Path(root) / "indices" / "candles" / "timeframe=1m" / f"symbol={sym}" / "data.parquet"
        )
        sym_dir = parquet.parent
        if sym_dir.exists():
            shutil.rmtree(sym_dir)
            print(f"  removed {sym_dir}")
        if catalog.unregister_symbol(sym):
            print(f"  unregistered catalog row: {sym}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--purge-excluded",
        action="store_true",
        help="Delete BSE100/200/500 parquet + catalog rows after bootstrap",
    )
    args = parser.parse_args()

    from datalake.ingestion.sync_manifest import (
        DEFAULT_BOOTSTRAP_EXCLUDE,
        bootstrap_sync_manifest_from_disk,
        manifest_path,
    )

    try:
        count = bootstrap_sync_manifest_from_disk(
            args.root,
            exclude=DEFAULT_BOOTSTRAP_EXCLUDE,
            overwrite=args.overwrite,
        )
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {manifest_path(args.root)} ({count} symbols)")
    if args.purge_excluded:
        print("Purging excluded index parquets...")
        _purge_excluded(args.root, DEFAULT_EXCLUDE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
