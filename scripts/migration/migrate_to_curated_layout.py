"""Migration: Convert legacy symbol-per-file layout to date-partitioned layout.

Reads all existing symbol=Parquet files and rewrites them as::

    market_data/curated/equities/candles/year=YYYY/month=MM/data_NNN.parquet

New layout properties:
- Partitioned by year/month for time-range pruning
- Sorted by (symbol, timestamp) within each file
- File sizes ~150MB for optimal Parquet performance
- Compatible with future Delta Lake migration

Usage:
    python -m scripts.migration.migrate_to_curated_layout [--dry-run] [--target-mb 150]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from datalake.paths import (
    CURATED_ROOT,
    curated_equity_path,
    symbol_partition_glob,
)

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    pa.field("timestamp", pa.timestamp("us")),
    pa.field("symbol", pa.utf8()),
    pa.field("exchange", pa.utf8()),
    pa.field("open", pa.float64()),
    pa.field("high", pa.float64()),
    pa.field("low", pa.float64()),
    pa.field("close", pa.float64()),
    pa.field("volume", pa.int64()),
    pa.field("oi", pa.int64()),
])


def _file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def migrate(
    root: str = "market_data",
    curated_root: str = CURATED_ROOT,
    timeframe: str = "1m",
    target_mb: int = 150,
    dry_run: bool = True,
) -> dict:
    """Merge all legacy symbol= files into date-partitioned curated files.

    Parameters
    ----------
    root:
        Root directory of the legacy datalake.
    curated_root:
        Root directory for the curated date-partitioned layout.
    timeframe:
        Timeframe to migrate.
    target_mb:
        Target size in MB for each output Parquet file.
    dry_run:
        If True, only report what would be done without writing.

    Returns
    -------
    dict with migration stats.
    """
    start_time = time.time()

    glob_pattern = symbol_partition_glob(root, timeframe)
    logger.info("Reading legacy files matching: %s", glob_pattern)

    rows = duckdb.execute(
        "SELECT count(*) FROM read_parquet(?)", [glob_pattern]
    ).fetchone()[0]
    total_rows = int(rows)

    total_files = len(
        list(Path(root).glob("equities/candles/timeframe=1m/symbol=*/data.parquet"))
    )

    logger.info("Found %d legacy files with %s total rows", total_files, f"{total_rows:,}")

    result = duckdb.execute(
        """
        SELECT year(timestamp) AS yr, month(timestamp) AS mon, count(*) AS cnt
        FROM read_parquet(?)
        GROUP BY yr, mon
        ORDER BY yr, mon
        """,
        [glob_pattern],
    ).fetchall()

    month_groups = [(int(r[0]), int(r[1]), int(r[2])) for r in result]
    logger.info("Data spans %d year-month partitions", len(month_groups))

    grand_total_before = sum(_file_size_mb(p) for p in Path(root).glob("equities/candles/timeframe=1m/symbol=*/data.parquet"))
    bytes_per_row = (grand_total_before * 1024 * 1024) / max(total_rows, 1)
    rows_per_file = max(1, int((target_mb * 1024 * 1024) / bytes_per_row))
    projected_files = 0

    for yr, mon, cnt in month_groups:
        num_files = max(1, -(-cnt // rows_per_file))
        projected_files += num_files
        logger.info(
            "  %04d-%02d: %s rows -> ~%d files (~%s rows each)",
            yr, mon, f"{cnt:,}", num_files, f"{rows_per_file:,}",
        )

    logger.info("Projected: %d curated files (vs %d legacy)", projected_files, total_files)
    logger.info("Legacy size: %.1f MB (%.1f bytes/row)", grand_total_before, bytes_per_row)

    if dry_run:
        return {
            "status": "dry_run",
            "legacy_files": total_files,
            "legacy_size_mb": round(grand_total_before, 1),
            "total_rows": total_rows,
            "month_partitions": len(month_groups),
            "projected_curated_files": projected_files,
            "target_mb": target_mb,
            "elapsed_seconds": round(time.time() - start_time, 2),
        }

    logger.info("Starting migration (this may take a while)...")
    curated_base = Path(curated_root) / "equities" / "candles"

    written_files = 0
    written_rows = 0
    total_size = 0

    for yr, mon, _ in month_groups:
        month_dir = curated_equity_path(root=curated_root, year=yr, month=mon)
        month_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Processing %04d-%02d ...", yr, mon)

        month_data = duckdb.execute(
            """
            SELECT *
            FROM read_parquet(?)
            WHERE year(timestamp) = ? AND month(timestamp) = ?
            ORDER BY symbol, timestamp
            """,
            [glob_pattern, yr, mon],
        ).fetchdf()

        if month_data.empty:
            continue

        table = pa.Table.from_pandas(month_data, schema=SCHEMA, preserve_index=False)
        num_rows = len(month_data)
        total_bytes = table.nbytes

        bytes_per_row_actual = max(1, total_bytes // num_rows)
        rows_per_file_actual = max(1, int((target_mb * 1024 * 1024) / bytes_per_row_actual))
        num_chunks = max(1, -(-num_rows // rows_per_file_actual))

        for chunk_idx in range(num_chunks):
            start_row = chunk_idx * rows_per_file_actual
            end_row = min(start_row + rows_per_file_actual, num_rows)
            chunk_table = table.slice(start_row, end_row - start_row)

            file_name = f"data_{chunk_idx:03d}.parquet"
            file_path = month_dir / file_name

            pq.write_table(
                chunk_table,
                file_path,
                compression="snappy",
                row_group_size=rows_per_file_actual // max(num_chunks, 1),
            )

            written_files += 1
            written_rows += len(chunk_table)
            total_size += chunk_table.nbytes

        del month_data, table

    elapsed = time.time() - start_time
    write_manifest(
        curated_base=curated_base,
        legacy_root=root,
        legacy_files=total_files,
        curated_files=written_files,
        total_rows=written_rows,
        total_size_mb=total_size / (1024 * 1024),
        elapsed_seconds=round(elapsed, 2),
        timeframe=timeframe,
    )

    logger.info(
        "Migration complete: %d files, %s rows, %.1f MB in %.1fs",
        written_files, f"{written_rows:,}", total_size / (1024 * 1024), elapsed,
    )

    return {
        "status": "completed",
        "legacy_files": total_files,
        "legacy_size_mb": round(grand_total_before, 1),
        "curated_files": written_files,
        "curated_size_mb": round(total_size / (1024 * 1024), 1),
        "total_rows": written_rows,
        "month_partitions": len(month_groups),
        "target_mb": target_mb,
        "elapsed_seconds": round(elapsed, 2),
    }


def write_manifest(
    curated_base: Path,
    legacy_root: str,
    legacy_files: int,
    curated_files: int,
    total_rows: int,
    total_size_mb: float,
    elapsed_seconds: float,
    timeframe: str,
) -> None:
    manifest = {
        "migration": "legacy_to_curated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "legacy": {
            "root": legacy_root,
            "pattern": f"timeframe={timeframe}/symbol=*/data.parquet",
            "file_count": legacy_files,
        },
        "curated": {
            "root": str(curated_base),
            "pattern": "year=*/month=*/data_*.parquet",
            "file_count": curated_files,
        },
        "total_rows": total_rows,
        "total_size_mb": round(total_size_mb, 1),
        "elapsed_seconds": elapsed_seconds,
        "tool": "scripts/migration/migrate_to_curated_layout.py",
    }
    manifest_path = curated_base.parent / "migration_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Manifest written to %s", manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy symbol-per-file layout to date-partitioned layout."
    )
    parser.add_argument(
        "--root",
        default="market_data",
        help="Legacy datalake root directory (default: market_data)",
    )
    parser.add_argument(
        "--curated-root",
        default=CURATED_ROOT,
        help="Curated datalake root directory (default: market_data/curated)",
    )
    parser.add_argument(
        "--timeframe",
        default="1m",
        choices=["1m", "5m", "15m", "1h", "1d"],
        help="Timeframe to migrate (default: 1m)",
    )
    parser.add_argument(
        "--target-mb",
        type=int,
        default=150,
        help="Target file size in MB (default: 150)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report without writing (default: true)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Actually perform the migration",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    stats = migrate(
        root=args.root,
        curated_root=args.curated_root,
        timeframe=args.timeframe,
        target_mb=args.target_mb,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print(json.dumps(stats, indent=2))
        print("\nRun with --no-dry-run to perform the migration.")
    else:
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
