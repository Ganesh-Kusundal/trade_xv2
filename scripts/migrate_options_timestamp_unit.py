#!/usr/bin/env python3
"""One-time migration: cast options candle Parquet timestamps ms -> us.

Root cause: sync_options.py's convert_format() parsed the source's
bar_time_ms field with pd.to_datetime(..., unit="ms"), producing
datetime64[ms] -- while every other datalake writer (equities, indices)
produces datetime64[us] from native Python datetime objects. Neither
writer ever applied the documented ARROW_SCHEMA, so nothing caught the
mismatch (see enforce_canonical_schema() in datalake/core/schema.py,
now wired into both writers going forward). This script backfills the
handful of options files written before that fix.

Lossless: ms -> us is a pure upcast (extra zero-padding on the sub-ms
digits), so row counts, values, and min/max timestamps are identical
before and after -- only the physical on-disk unit changes.

Usage:
    python scripts/migrate_options_timestamp_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from datalake.core.io import atomic_parquet_write
from datalake.core.schema import ARROW_SCHEMA


def main() -> int:
    root = Path(__file__).resolve().parent.parent / "data" / "lake" / "options" / "candles"
    files = sorted(root.glob("**/*.parquet"))
    if not files:
        print(f"No parquet files found under {root}")
        return 1

    target_unit = ARROW_SCHEMA.field("timestamp").type
    migrated = 0
    skipped = 0

    for path in files:
        table = pq.read_table(path)
        current_type = table.schema.field("timestamp").type
        row_count = table.num_rows

        if current_type == target_unit:
            print(f"SKIP  {path.relative_to(root.parent.parent.parent)}  already {current_type}  ({row_count} rows)")
            skipped += 1
            continue

        min_before = table.column("timestamp")[0].as_py() if row_count else None
        max_before = table.column("timestamp")[-1].as_py() if row_count else None

        new_fields = [
            pa.field("timestamp", target_unit) if f.name == "timestamp" else f for f in table.schema
        ]
        migrated_table = table.cast(pa.schema(new_fields))

        min_after = migrated_table.column("timestamp")[0].as_py() if row_count else None
        max_after = migrated_table.column("timestamp")[-1].as_py() if row_count else None
        assert min_before == min_after and max_before == max_after, (
            f"Value mismatch after cast for {path}: "
            f"before=({min_before}, {max_before}) after=({min_after}, {max_after})"
        )

        atomic_parquet_write(path, migrated_table, compression="snappy")
        print(
            f"MIGRATE {path.relative_to(root.parent.parent.parent)}  "
            f"{current_type} -> {target_unit}  ({row_count} rows, "
            f"{min_after}..{max_after})"
        )
        migrated += 1

    print(f"\nDone: {migrated} migrated, {skipped} already correct, {len(files)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
