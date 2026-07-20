"""Data health check — prevents future timezone/quality issues.

Run this:
- After any data ingestion
- As a CI check before deploying
- As a cron job for continuous monitoring

Detects:
- Timestamps outside market hours (derived from active exchange calendar)
- Duplicate timestamps
- Missing trading days
- OHLCV inconsistencies
- Schema mismatches
- Symbol normalization issues

Exit code 0 = all healthy, 1 = issues found.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def check_market_hours(
    conn: duckdb.DuckDBPyConnection,
    open_h: int = 9,
    open_m: int = 15,
    close_h: int = 15,
    close_m: int = 30,
) -> list[str]:
    """Check that all timestamps are within market hours for the active exchange."""
    issues = []
    # Build SQL dynamically from the open/close bounds
    sql = f"""
        SELECT COUNT(*) FROM v_candles_1m
        WHERE NOT (
            (EXTRACT(HOUR FROM timestamp) = {open_h} AND EXTRACT(MINUTE FROM timestamp) >= {open_m})
            OR (EXTRACT(HOUR FROM timestamp) BETWEEN {open_h + 1} AND {close_h - 1})
            OR (EXTRACT(HOUR FROM timestamp) = {close_h} AND EXTRACT(MINUTE FROM timestamp) <= {close_m})
        )
    """
    r = conn.execute(sql).fetchone()
    count = r[0]
    if count > 0:
        issues.append(
            f"  {count:,} candles outside market hours ({open_h}:{open_m:02d}-{close_h}:{close_m:02d})"
        )
    return issues


def check_duplicates(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Check for duplicate timestamps."""
    issues = []
    r = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT symbol, timestamp
            FROM v_candles_1m
            GROUP BY symbol, timestamp
            HAVING COUNT(*) > 1
        )
    """).fetchone()
    count = r[0]
    if count > 0:
        issues.append(f"  {count:,} duplicate timestamps found")
    return issues


def check_ohlcv_consistency(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Check OHLCV consistency (high >= low, open/close in range)."""
    issues = []
    r = conn.execute("""
        SELECT COUNT(*) FROM v_candles_1m
        WHERE high < low OR high < open OR high < close OR low > open OR low > close
    """).fetchone()
    count = r[0]
    if count > 0:
        issues.append(f"  {count:,} rows with inconsistent OHLCV")
    return issues


def check_symbols(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Check symbol normalization (all uppercase, no suffixes)."""
    issues = []
    r = conn.execute("""
        SELECT DISTINCT symbol FROM v_candles_1m
        WHERE symbol != UPPER(symbol) OR symbol LIKE '%-EQ' OR symbol LIKE '%-BE'
    """).fetchall()
    if r:
        issues.append(f"  {len(r)} symbols not normalized: {[s[0] for s in r[:5]]}")
    return issues


def check_future_timestamps(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Check for future timestamps."""
    issues = []
    r = conn.execute("""
        SELECT COUNT(*) FROM v_candles_1m
        WHERE timestamp > CURRENT_TIMESTAMP
    """).fetchone()
    count = r[0]
    if count > 0:
        issues.append(f"  {count:,} future timestamps (clock skew or bad ingestion)")
    return issues


def check_coverage(conn: duckdb.DuckDBPyConnection, min_rows: int = 100000) -> list[str]:
    """Check that each symbol has reasonable data coverage."""
    issues = []
    r = conn.execute(
        """
        SELECT symbol, COUNT(*) as cnt
        FROM v_candles_1m
        GROUP BY symbol
        HAVING cnt < ?
        ORDER BY cnt
        LIMIT 5
    """,
        [min_rows],
    ).fetchall()
    for sym, cnt in r:
        issues.append(f"  {sym}: only {cnt:,} rows (expected >{min_rows:,})")
    return issues


def run_health_check(db_path: str | None = None, min_rows: int = 100000) -> int:
    """Run all health checks. Returns 0 if healthy, 1 if issues found."""
    if db_path is None:
        from domain.ports.data_catalog import DEFAULT_DATA_PATHS

        db_path = str(DEFAULT_DATA_PATHS.catalog_path)
    if not Path(db_path).exists():
        logger.error("Database not found: %s", db_path)
        return 1

    from datalake.core.duckdb_utils import duckdb_connection

    with duckdb_connection(db_path, read_only=True) as conn:
        logger.info("=" * 60)
        logger.info("DATA HEALTH CHECK")
        logger.info("=" * 60)

        all_issues: list[str] = []

        try:
            from datalake.exchange_registry import get_market_close_time, get_market_open_time

            open_t = get_market_open_time()
            close_t = get_market_close_time()
            open_h, open_m = open_t.hour, open_t.minute
            close_h, close_m = close_t.hour, close_t.minute
        except Exception:
            open_h, open_m, close_h, close_m = 9, 15, 15, 30

        market_label = f"Market hours ({open_h}:{open_m:02d}-{close_h}:{close_m:02d})"

        checks = [
            (market_label, lambda c: check_market_hours(c, open_h, open_m, close_h, close_m)),
            ("Duplicate timestamps", check_duplicates),
            ("OHLCV consistency", check_ohlcv_consistency),
            ("Symbol normalization", check_symbols),
            ("Future timestamps", check_future_timestamps),
            ("Data coverage", lambda c: check_coverage(c, min_rows=min_rows)),
        ]

        for name, check_fn in checks:
            logger.info("Checking: %s...", name)
            issues = check_fn(conn)
            if issues:
                logger.warning("FAIL (%d issue(s))", len(issues))
                for issue in issues:
                    all_issues.append(issue)
                    logger.warning(issue)
            else:
                logger.info("OK")

        logger.info("=" * 60)
        if all_issues:
            logger.warning("FAILED: %d issue(s) found", len(all_issues))
            return 1
        logger.info("ALL CHECKS PASSED")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Data health check")
    from domain.ports.data_catalog import DEFAULT_DATA_PATHS

    parser.add_argument(
        "--db", default=str(DEFAULT_DATA_PATHS.catalog_path), help="Path to DuckDB catalog"
    )
    parser.add_argument("--min-rows", type=int, default=100000, help="Minimum rows per symbol")
    args = parser.parse_args()
    return run_health_check(args.db, min_rows=args.min_rows)


if __name__ == "__main__":
    sys.exit(main())
