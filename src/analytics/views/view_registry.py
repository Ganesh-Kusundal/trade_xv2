"""View registry — registration, discovery, and metadata management for analytics views."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from datalake.core.duckdb_utils import duckdb_connection, get_pool
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH

logger = logging.getLogger(__name__)


class ViewRegistry:
    """Manages view registration, discovery, and introspection.

    Handles all metadata queries against DuckDB's system tables
    (duckdb_views, information_schema) and provides lookup methods.
    """

    # Materialized table names managed by the system
    MATERIALIZED_TABLES = [
        "m_intraday",
        "m_recent_daily",
        "m_symbol_snapshot",
        "m_intraday_snapshot",
        "m_duplicate_candles",
        "m_missing_candles",
        "m_trading_days",
        "m_pcr",
        "m_max_pain",
        "m_iv_surface",
    ]

    def __init__(self, catalog_path: str | Path | None = None, read_only: bool = False) -> None:
        self._path = Path(catalog_path) if catalog_path else DEFAULT_CATALOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Return the cached read-write connection for DDL operations."""
        if self._conn is None:
            self._conn = get_pool().acquire(self._path, read_only=False)
        return self._conn

    def close(self) -> None:
        """Release the cached connection back to the pool."""
        if self._conn is not None:
            get_pool().release(self._path)
            self._conn = None

    def _query_connection(self):
        """Context manager yielding a connection for read queries."""
        if self._read_only:
            return duckdb_connection(self._path, read_only=True)
        else:
            from contextlib import contextmanager

            @contextmanager
            def _rw_conn():
                yield self.conn

            return _rw_conn()

    # ─── Introspection ───────────────────────────────────────────────────────

    def list_views(self) -> list[dict]:
        """List all user-created views in the catalog."""
        with self._query_connection() as conn:
            results = conn.execute(
                "SELECT view_name, sql FROM duckdb_views() WHERE schema_name = 'main' AND internal = false"
            ).fetchall()
            return [{"name": r[0], "definition": r[1] or ""} for r in results]

    def view_exists(self, view_name: str) -> bool:
        """Check if a view exists in the main schema."""
        with self._query_connection() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ? AND schema_name = 'main'",
                [view_name],
            ).fetchone()
            return result[0] > 0

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the main schema."""
        with self._query_connection() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ? AND table_schema = 'main'",
                [table_name],
            ).fetchone()
            return result[0] > 0

    def view_columns(self, view_name: str) -> list[str]:
        """Get column names for a view or table."""
        try:
            with self._query_connection() as conn:
                result = conn.execute(f"DESCRIBE {view_name}").fetchall()
                return [r[0] for r in result]
        except Exception:
            return []

    def view_count(self) -> int:
        """Count total number of user-created views."""
        with self._query_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE schema_name = 'main' AND internal = false"
            ).fetchone()[0]

    def table_count(self) -> int:
        """Count total number of tables in the main schema."""
        with self._query_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchone()[0]

    def drop_all_views(self) -> None:
        """Drop all user-created analytics views and materialized tables."""
        views = self.list_views()
        for v in views:
            if v["name"].startswith("duckdb_") or v["name"].startswith("information_"):
                continue
            try:
                self.conn.execute(f"DROP VIEW IF EXISTS {v['name']}")
            except Exception as exc:
                logger.debug("view_drop_failed: %s: %s", v["name"], exc)

        for tbl in self.MATERIALIZED_TABLES:
            self.conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        logger.info("Dropped views and materialized tables")
