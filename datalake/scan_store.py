"""Scan result persistence — store and query scan snapshots in DuckDB."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent.parent / "market_data" / "catalog.duckdb"


def _connect_with_retry(path: str, read_only: bool, max_attempts: int = 10) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, retrying with exponential backoff on lock conflicts."""
    delay = 0.05
    for attempt in range(max_attempts):
        try:
            return duckdb.connect(path, read_only=read_only)
        except (duckdb.IOException, duckdb.OperationalError, duckdb.ConnectionException) as exc:
            msg = str(exc).lower()
            is_lock_error = "lock" in msg or "could not set" in msg
            if not is_lock_error or attempt == max_attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
    raise RuntimeError("unreachable")


def _get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return _connect_with_retry(str(CATALOG_PATH), read_only=read_only)


def ensure_scan_table(conn: duckdb.DuckDBPyConnection | None = None) -> None:
    """Create the scan_results table if it doesn't exist."""
    close = False
    if conn is None:
        conn = _get_connection()
        close = True
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_results (
                scan_id VARCHAR,
                scanner VARCHAR,
                symbol VARCHAR,
                score DOUBLE,
                reasons VARCHAR,
                universe_size INTEGER,
                scanned_at TIMESTAMP,
                metadata VARCHAR,
                PRIMARY KEY (scan_id, symbol)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scan_results_scanner
            ON scan_results(scanner)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scan_results_scanned_at
            ON scan_results(scanned_at)
        """)
    finally:
        if close:
            conn.close()


def save_scan_result(
    scanner: str,
    candidates: list,
    universe_size: int,
    metadata: dict | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> str:
    """Save scan results to DuckDB. Returns the scan_id."""
    close = False
    if conn is None:
        conn = _get_connection()
        close = True

    try:
        ensure_scan_table(conn)

        import uuid
        scan_id = f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}_{scanner}_{uuid.uuid4().hex[:8]}"
        scanned_at = datetime.now(timezone.utc)

        rows = []
        for candidate in candidates:
            rows.append((
                scan_id,
                scanner,
                candidate.symbol,
                candidate.score,
                json.dumps(candidate.reasons) if candidate.reasons else "[]",
                universe_size,
                scanned_at,
                json.dumps(metadata) if metadata else "{}",
            ))

        conn.executemany(
            "INSERT INTO scan_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        logger.info("Saved %d scan results with id %s", len(rows), scan_id)
        return scan_id
    finally:
        if close:
            conn.close()


def get_recent_scans(
    scanner: str | None = None,
    limit: int = 10,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict]:
    """Get recent scan results from DuckDB."""
    close = False
    if conn is None:
        conn = _get_connection(read_only=True)
        close = True

    try:
        ensure_scan_table(conn)

        if scanner:
            rows = conn.execute(
                "SELECT DISTINCT scan_id, scanner, scanned_at, universe_size "
                "FROM scan_results WHERE scanner = ? "
                "ORDER BY scanned_at DESC LIMIT ?",
                [scanner, limit],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT scan_id, scanner, scanned_at, universe_size "
                "FROM scan_results "
                "ORDER BY scanned_at DESC LIMIT ?",
                [limit],
            ).fetchall()

        return [
            {
                "scan_id": row[0],
                "scanner": row[1],
                "scanned_at": row[2],
                "universe_size": row[3],
            }
            for row in rows
        ]
    finally:
        if close:
            conn.close()


def get_scan_symbols(
    scan_id: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict]:
    """Get symbols from a specific scan."""
    close = False
    if conn is None:
        conn = _get_connection(read_only=True)
        close = True

    try:
        rows = conn.execute(
            "SELECT symbol, score, reasons FROM scan_results "
            "WHERE scan_id = ? ORDER BY score DESC",
            [scan_id],
        ).fetchall()

        return [
            {
                "symbol": row[0],
                "score": row[1],
                "reasons": json.loads(row[2]) if row[2] else [],
            }
            for row in rows
        ]
    finally:
        if close:
            conn.close()


def compare_scans(
    scan_id_1: str,
    scan_id_2: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict:
    """Compare two scan results — find新增/removed/changed symbols."""
    close = False
    if conn is None:
        conn = _get_connection(read_only=True)
        close = True

    try:
        symbols1 = {r["symbol"]: r["score"] for r in get_scan_symbols(scan_id_1, conn)}
        symbols2 = {r["symbol"]: r["score"] for r in get_scan_symbols(scan_id_2, conn)}

        added = set(symbols2.keys()) - set(symbols1.keys())
        removed = set(symbols1.keys()) - set(symbols2.keys())
        common = set(symbols1.keys()) & set(symbols2.keys())

        changed = []
        for sym in common:
            delta = symbols2[sym] - symbols1[sym]
            if abs(delta) > 0.1:
                changed.append({"symbol": sym, "old_score": symbols1[sym], "new_score": symbols2[sym], "delta": delta})

        return {
            "scan_id_1": scan_id_1,
            "scan_id_2": scan_id_2,
            "added": sorted(added),
            "removed": sorted(removed),
            "changed": sorted(changed, key=lambda x: abs(x["delta"]), reverse=True),
            "summary": f"Added {len(added)}, Removed {len(removed)}, Changed {len(changed)}",
        }
    finally:
        if close:
            conn.close()
