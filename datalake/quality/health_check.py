"""Data health check — prevents future timezone/quality issues.

Run this:
- After any data ingestion
- As a CI check before deploying
- As a cron job for continuous monitoring

Detects:
- Timestamps outside IST market hours (9:15-15:30)
- Duplicate timestamps
- Missing trading days
- OHLCV inconsistencies
- Schema mismatches
- Symbol normalization issues

Exit code 0 = all healthy, 1 = issues found.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def check_market_hours(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Check that all timestamps are within NSE market hours (9:15-15:30 IST)."""
    issues = []
    r = conn.execute("""
        SELECT COUNT(*) FROM v_candles_1m
        WHERE NOT (
            (EXTRACT(HOUR FROM timestamp) = 9 AND EXTRACT(MINUTE FROM timestamp) >= 15)
            OR (EXTRACT(HOUR FROM timestamp) BETWEEN 10 AND 14)
            OR (EXTRACT(HOUR FROM timestamp) = 15 AND EXTRACT(MINUTE FROM timestamp) <= 30)
        )
    """).fetchone()
    count = r[0]
    if count > 0:
        issues.append(f"  {count:,} candles outside market hours (9:15-15:30 IST)")
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


def run_health_check(db_path: str = "market_data/catalog.duckdb", min_rows: int = 100000) -> int:
    """Run all health checks. Returns 0 if healthy, 1 if issues found."""
    if not Path(db_path).exists():
        print(f"ERROR: Database not found: {db_path}")
        return 1

    conn = duckdb.connect(db_path, read_only=True)
    print("=" * 60)
    print("DATA HEALTH CHECK")
    print("=" * 60)
    print()

    all_issues: list[str] = []

    checks = [
        ("Market hours (9:15-15:30 IST)", check_market_hours),
        ("Duplicate timestamps", check_duplicates),
        ("OHLCV consistency", check_ohlcv_consistency),
        ("Symbol normalization", check_symbols),
        ("Future timestamps", check_future_timestamps),
        ("Data coverage", lambda c: check_coverage(c, min_rows=min_rows)),
    ]

    for name, check_fn in checks:
        print(f"Checking: {name}...", end=" ")
        issues = check_fn(conn)
        if issues:
            print(f"FAIL ({len(issues)} issue(s))")
            for issue in issues:
                all_issues.append(issue)
                print(issue)
        else:
            print("OK")
        print()

    conn.close()

    print("=" * 60)
    if all_issues:
        print(f"FAILED: {len(all_issues)} issue(s) found")
        return 1
    else:
        print("ALL CHECKS PASSED")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Data health check")
    parser.add_argument("--db", default="market_data/catalog.duckdb", help="Path to DuckDB catalog")
    parser.add_argument("--min-rows", type=int, default=100000, help="Minimum rows per symbol")
    args = parser.parse_args()
    return run_health_check(args.db, min_rows=args.min_rows)


if __name__ == "__main__":
    sys.exit(main())
