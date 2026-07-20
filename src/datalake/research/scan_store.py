"""Scan result persistence — store and query scan snapshots in DuckDB."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import duckdb

from datalake.core.duckdb_utils import DEFAULT_CATALOG_PATH

logger = logging.getLogger(__name__)


def _get_connection() -> duckdb.DuckDBPyConnection:
    from datalake.core.duckdb_utils import get_pool

    return get_pool().acquire(str(DEFAULT_CATALOG_PATH), read_only=False)


def ensure_scan_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the scan_results table if it doesn't exist."""
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


def save_scan_result(
    scanner: str,
    candidates: list,
    universe_size: int,
    metadata: dict | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> str:
    """Save scan results to DuckDB. Returns the scan_id."""
    own_conn = conn is None
    if own_conn:
        conn = _get_connection()

    try:
        ensure_scan_table(conn)

        scan_id = f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}_{scanner}_{uuid.uuid4().hex[:8]}"
        scanned_at = datetime.now(timezone.utc)

        rows = [
            (
                scan_id,
                scanner,
                candidate.symbol,
                candidate.score,
                json.dumps(candidate.reasons) if candidate.reasons else "[]",
                universe_size,
                scanned_at,
                json.dumps(metadata) if metadata else "{}",
            )
            for candidate in candidates
        ]

        conn.executemany(
            "INSERT INTO scan_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        logger.info("Saved %d scan results with id %s", len(rows), scan_id)
        return scan_id
    finally:
        if own_conn:
            conn.close()


def get_recent_scans(
    scanner: str | None = None,
    limit: int = 10,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict]:
    """Get recent scan results from DuckDB."""
    own_conn = conn is None
    if own_conn:
        conn = _get_connection()

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
        if own_conn:
            conn.close()


def get_scan_symbols(
    scan_id: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> list[dict]:
    """Get symbols from a specific scan."""
    own_conn = conn is None
    if own_conn:
        conn = _get_connection()

    try:
        rows = conn.execute(
            "SELECT symbol, score, reasons FROM scan_results WHERE scan_id = ? ORDER BY score DESC",
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
        if own_conn:
            conn.close()


def compare_scans(
    scan_id_1: str,
    scan_id_2: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """Compare two scan results via SQL — find added/removed/changed symbols."""
    own_conn = conn is None
    if own_conn:
        conn = _get_connection()

    try:
        ensure_scan_table(conn)

        result = conn.execute(
            """
            WITH s1 AS (
                SELECT symbol, score FROM scan_results WHERE scan_id = ?
            ),
            s2 AS (
                SELECT symbol, score FROM scan_results WHERE scan_id = ?
            ),
            added AS (
                SELECT s2.symbol, NULL::DOUBLE as old_score, s2.score as new_score,
                       NULL::DOUBLE as delta, 'added' as change_type
                FROM s2 LEFT JOIN s1 ON s2.symbol = s1.symbol
                WHERE s1.symbol IS NULL
            ),
            removed AS (
                SELECT s1.symbol, s1.score as old_score, NULL::DOUBLE as new_score,
                       NULL::DOUBLE as delta, 'removed' as change_type
                FROM s1 LEFT JOIN s2 ON s1.symbol = s2.symbol
                WHERE s2.symbol IS NULL
            ),
            changed AS (
                SELECT
                    s2.symbol,
                    s1.score as old_score,
                    s2.score as new_score,
                    s2.score - s1.score as delta,
                    'changed' as change_type
                FROM s2 INNER JOIN s1 ON s2.symbol = s1.symbol
                WHERE ABS(s2.score - s1.score) > 0.1
            )
            SELECT * FROM added
            UNION ALL
            SELECT * FROM removed
            UNION ALL
            SELECT * FROM changed
        """,
            [scan_id_1, scan_id_2],
        ).fetchall()

        added = [r[0] for r in result if r[4] == "added"]
        removed = [r[0] for r in result if r[4] == "removed"]
        changed = [
            {"symbol": r[0], "old_score": r[1], "new_score": r[2], "delta": r[3]}
            for r in result
            if r[4] == "changed"
        ]

        return {
            "scan_id_1": scan_id_1,
            "scan_id_2": scan_id_2,
            "added": sorted(added),
            "removed": sorted(removed),
            "changed": sorted(changed, key=lambda x: abs(x["delta"]), reverse=True),
            "summary": f"Added {len(added)}, Removed {len(removed)}, Changed {len(changed)}",
        }
    finally:
        if own_conn:
            conn.close()
