"""Tests for catalog schema migrations."""

from __future__ import annotations

import duckdb

from datalake.migrations import CURRENT_SCHEMA_VERSION, apply_migrations, get_schema_version


def test_apply_migrations_creates_version_table(tmp_path):
    db_path = tmp_path / "catalog.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        version = apply_migrations(conn)
        assert version == CURRENT_SCHEMA_VERSION
        assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert "schema_migrations" in tables
        assert "universe_symbols" in tables
    finally:
        conn.close()
