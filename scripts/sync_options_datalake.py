#!/usr/bin/env python3
"""CLI entrypoint for federated options datalake sync."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from runtime.options_sync import run_federated_options_sync


def main() -> int:
    summary = run_federated_options_sync(print_fn=print)
    print(
        f"\nDone: {summary['files_created']} created, "
        f"{summary['files_merged']} merged, "
        f"{summary['new_rows']:,} new rows, "
        f"{summary['total_rows_after']:,} total"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
