"""Lightweight schema version tracking for catalog DuckDB."""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS universe_symbols (
            universe VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            PRIMARY KEY (universe, symbol)
        )
        """,
    ],
}


def get_schema_version(conn: duckdb.DuckDBPyConnection) -> int:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def apply_migrations(conn: duckdb.DuckDBPyConnection) -> int:
    """Apply pending migrations. Returns new schema version."""
    current = get_schema_version(conn)
    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        for sql in MIGRATIONS[version]:
            conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            [version],
        )
        logger.info("Applied catalog schema migration v%d", version)
        current = version
    return current
