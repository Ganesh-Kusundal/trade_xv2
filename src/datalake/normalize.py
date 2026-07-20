"""One-shot migration: normalize all Parquet timestamps to IST.

Existing data has mixed timezones:
- Some files: bar_time_ms was in UTC → correctly converted to IST (9:15-15:29)
- Some files: bar_time_ms was in IST → incorrectly treated as UTC, shifted by 5:30
  (stored as 14:46-20:59 instead of 9:16-15:29)

This script detects the timezone per file and normalizes all timestamps to IST
(naive datetime, since we store wall-clock IST).

Usage:
    python -m datalake.normalize
    python -m datalake.normalize --dry-run   # report without writing
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import duckdb

from datalake.core.io import atomic_parquet_write
from datalake.core.paths import (
    DEFAULT_DATA_ROOT,
    DEFAULT_TIMEFRAME,
    symbol_partition_path,
    timeframe_partition_dir,
)
from datalake.core.schema import CANONICAL_COLUMNS

logger = logging.getLogger(__name__)

MARKET_TZ = "Asia/Kolkata"


def detect_timezone(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    data_root: str = DEFAULT_DATA_ROOT,
) -> str:
    """Detect whether a symbol's data is in IST, UTC, or IST-shifted.

    Uses non-overlapping hour ranges to avoid double-counting:
    - IST_SHIFTED: hours 14-20 (IST source + 5:30h, incorrectly converted)
    - UTC:         hours 3-8   (raw UTC, not converted)
    - IST:         hours 9-15  (correctly stored IST)

    Hours 9-10 are technically ambiguous (both IST market open and UTC
    market close), so we check the modal hour in non-overlapping ranges.

    Returns one of: 'IST', 'UTC', 'IST_SHIFTED', 'UNKNOWN', 'MIXED'.
    """
    pattern = str(symbol_partition_path(data_root, symbol, DEFAULT_TIMEFRAME))
    try:
        rows = conn.execute(
            """
            SELECT EXTRACT(HOUR FROM timestamp) as hr, COUNT(*) as cnt
            FROM read_parquet(?)
            GROUP BY hr ORDER BY cnt DESC
        """,
            [pattern],
        ).fetchall()
    except Exception:
        return "UNKNOWN"

    if not rows:
        return "UNKNOWN"

    total = sum(cnt for _, cnt in rows)
    if total == 0:
        return "UNKNOWN"

    # Check in priority order: shifted > utc > ist
    shifted_count = sum(cnt for hr, cnt in rows if 14 <= hr <= 20)
    utc_count = sum(cnt for hr, cnt in rows if 3 <= hr <= 8)
    ist_count = sum(cnt for hr, cnt in rows if 9 <= hr <= 15)

    if shifted_count > total * 0.3:
        return "IST_SHIFTED"
    if utc_count > total * 0.3:
        return "UTC"
    if ist_count > total * 0.3:
        return "IST"
    return "MIXED"


def normalize_timestamps(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    data_root: str = DEFAULT_DATA_ROOT,
    dry_run: bool = False,
) -> str:
    """Normalize one symbol's Parquet file to IST timestamps.

    Returns the detected timezone, or 'SKIPPED' if no fix needed.
    """
    tz = detect_timezone(conn, symbol, data_root)

    if tz == "IST":
        return "IST"
    if tz == "UNKNOWN":
        return "SKIPPED"

    path = symbol_partition_path(data_root, symbol, DEFAULT_TIMEFRAME)
    if not path.exists():
        return "SKIPPED"

    if dry_run:
        logger.info("[DRY-RUN] %s: detected %s, would normalize", symbol, tz)
        return tz

    return _apply_correction(conn, symbol, tz, path)


from domain.constants.market import IST_SQL_INTERVAL

_IST_SHIFTED_SQL = f"""
    CREATE TABLE _tmp AS
    SELECT * EXCLUDE (timestamp),
           CAST(timestamp - {IST_SQL_INTERVAL} AS TIMESTAMP) as timestamp
    FROM read_parquet(?)
"""

_UTC_TO_IST_SQL = """
    CREATE TABLE _tmp AS
    SELECT * EXCLUDE (timestamp),
           CAST(timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS TIMESTAMP) as timestamp
    FROM read_parquet(?)
"""


def _apply_correction(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    tz: str,
    path: Path,
) -> str:
    """Apply the appropriate timezone correction and rewrite the parquet file."""
    if tz == "IST_SHIFTED":
        correction_sql = _IST_SHIFTED_SQL
    elif tz == "UTC":
        correction_sql = _UTC_TO_IST_SQL
    else:
        logger.warning("%s: MIXED timezone, manual review needed", symbol)
        return "MIXED"

    return _rewrite_parquet(conn, symbol, tz, path, correction_sql)


def _rewrite_parquet(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    tz: str,
    path: Path,
    correction_sql: str,
) -> str:
    """Execute correction SQL, then overwrite the parquet file with corrected data."""
    conn.execute(correction_sql, [str(path)])

    n = conn.execute("SELECT COUNT(*) FROM _tmp").fetchone()[0]
    if n == 0:
        conn.execute("DROP TABLE _tmp")
        return "EMPTY"

    import pyarrow as pa

    reader = conn.execute("SELECT * FROM _tmp").arrow()
    table = reader.read_all() if hasattr(reader, "read_all") else pa.Table.from_batches(reader)
    expected = [c for c in CANONICAL_COLUMNS if c in table.column_names]
    table = table.select(expected)

    atomic_parquet_write(path, table, compression="snappy")
    conn.execute("DROP TABLE _tmp")

    logger.info("%s: normalized from %s (%d rows)", symbol, tz, n)
    return tz


def normalize_all(dry_run: bool = False, data_root: str = DEFAULT_DATA_ROOT) -> dict[str, int]:
    """Normalize all symbols. Returns a count of each timezone detected."""
    root = timeframe_partition_dir(data_root, DEFAULT_TIMEFRAME)
    if not root.exists():
        logger.error("No data found at %s", root)
        return {}

    symbols = sorted(
        p.name.replace("symbol=", "")
        for p in root.iterdir()
        if p.is_dir() and p.name.startswith("symbol=")
    )

    from datalake.core.duckdb_utils import get_memory_pool

    pool = get_memory_pool()
    conn = pool.acquire()
    counts: dict[str, int] = {}

    for symbol in symbols:
        try:
            result = normalize_timestamps(conn, symbol, data_root=data_root, dry_run=dry_run)
            counts[result] = counts.get(result, 0) + 1
        except Exception as exc:
            logger.error("Failed to normalize %s: %s", symbol, exc)
            counts["ERROR"] = counts.get("ERROR", 0) + 1

    pool.release(conn)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize all Parquet timestamps to IST")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    # Initialize logging if not already configured
    if not logging.getLogger().handlers:
        from infrastructure.logging_config import configure_logging

        configure_logging()

    logger.info("Scanning all symbols...")
    counts = normalize_all(dry_run=args.dry_run)

    logger.info("Results:")
    for tz, n in sorted(counts.items()):
        logger.info("  %-15s %4d symbols", tz, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
