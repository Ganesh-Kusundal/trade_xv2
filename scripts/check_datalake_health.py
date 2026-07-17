#!/usr/bin/env python3
"""Post-sync datalake health check -- CLI wrapper around the working
DatalakeTools.health_check() (queries the real on-disk Parquet files,
unlike the legacy datalake.quality.health_check.run_health_check()
which targets an empty curated/ view).

Run this after any sync (scripts/sync_datalake.py) to catch corruption --
duplicate timestamps, OHLC inconsistency,
negative volume, future timestamps, candles outside NSE session hours
(the exact fingerprint of the Dhan/Upstox timezone bug fixed in this
session) -- before it accumulates silently for months.

Exit code 0 = clean, 1 = issues found.

Usage:
    python scripts/check_datalake_health.py [--timeframe 1m] [--min-rows 10000]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from datalake.mcp.tools import DEFAULT_ROOT, DatalakeTools


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--min-rows", type=int, default=10000)
    args = parser.parse_args()

    tools = DatalakeTools(root=args.root)
    results = tools.health_check(timeframe=args.timeframe, min_rows=args.min_rows)

    had_issues = False
    print(f"Datalake health check ({args.root}, timeframe={args.timeframe})")
    for name, result in results.items():
        if name == "thin_coverage":
            n = len(result["sample"])
            if n:
                had_issues = True
                print(f"  FAIL thin_coverage: {n} symbol(s) below {result['min_rows_threshold']} rows")
                for row in result["sample"][:5]:
                    print(f"    {row}")
            else:
                print("  OK   thin_coverage")
            continue
        count = result["count"]
        if count:
            had_issues = True
            print(f"  FAIL {name}: {count} row(s)")
            for row in result["sample"][:5]:
                print(f"    {row}")
        else:
            print(f"  OK   {name}")

    print("ISSUES FOUND" if had_issues else "ALL CHECKS PASSED")
    return 1 if had_issues else 0


if __name__ == "__main__":
    sys.exit(main())
