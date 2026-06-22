"""Shared DuckDB connection utilities — process-wide connection pool.

Provides:
- ``connect_with_retry`` for handling DuckDB's single-writer lock
- ``DuckDBPool`` for process-wide connection reuse (single connection per file)
- ``get_pool`` / ``get_connection`` for convenient access
- ``close_all_connections`` for clean shutdown

Used by DataCatalog, ViewManager, and ScanStore.

DuckDB does NOT allow multiple connections to the same file with different
configurations (e.g. read_only=True vs read_only=False). This module enforces
a single connection per file path, always opened in read-write mode so both
catalog writes and view queries work through the same handle.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path("market_data/catalog.duckdb")


def connect_with_retry(
    path: str,
    read_only: bool = False,
    max_attempts: int = 10,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, retrying with exponential backoff on lock conflicts.

    DuckDB is single-writer. A writer holds an exclusive lock, so a concurrent
    reader may see ``IO Error: Could not set lock on file``. This retries with
    backoff so read commands don't fail transiently.
    """
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


class DuckDBReadPool:
    """Read-only DuckDB pool — allows multiple concurrent read connections.

    Unlike DuckDBPool (which has one connection per file), this pool creates
    a NEW read-only connection for each acquire() call. This enables true
    concurrent reads from multiple FastAPI request handlers.

    Connections are short-lived: callers should release() immediately after
    reading to allow cleanup.

    Usage:
        pool = DuckDBReadPool()
        conn = pool.acquire("market_data/catalog.duckdb")
        try:
            result = conn.execute("SELECT ...").fetchdf()
        finally:
            pool.release("market_data/catalog.duckdb")
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_connections: dict[str, list[duckdb.DuckDBPyConnection]] = {}

    def acquire(self, db_path: str | Path) -> duckdb.DuckDBPyConnection:
        """Create a new read-only connection for concurrent reads."""
        key = str(Path(db_path).resolve())
        conn = connect_with_retry(key, read_only=True)
        with self._lock:
            if key not in self._active_connections:
                self._active_connections[key] = []
            self._active_connections[key].append(conn)
        logger.debug("DuckDBReadPool: created read-only connection to %s", key)
        return conn

    def release(self, db_path: str | Path, conn: duckdb.DuckDBPyConnection | None = None) -> None:
        """Close a read-only connection.

        Parameters
        ----------
        db_path:
            Path to DuckDB file.
        conn:
            Connection to close. If None, closes most recent connection.
        """
        key = str(Path(db_path).resolve())
        with self._lock:
            if key in self._active_connections and self._active_connections[key]:
                if conn:
                    if conn in self._active_connections[key]:
                        self._active_connections[key].remove(conn)
                else:
                    conn = self._active_connections[key].pop()
                try:
                    conn.close()
                except Exception as exc:
                    logger.debug("DuckDBReadPool: close failed for %s: %s", key, exc)
                logger.debug("DuckDBReadPool: closed read-only connection to %s", key)

    def close_all(self) -> None:
        """Close all active read-only connections."""
        with self._lock:
            count = 0
            for key, conns in self._active_connections.items():
                for conn in conns:
                    try:
                        conn.close()
                        count += 1
                    except Exception as exc:
                        logger.debug("DuckDBReadPool: close failed for %s: %s", key, exc)
            self._active_connections.clear()
            logger.info("DuckDBReadPool: closed %d read-only connections", count)


class DuckDBPool:
    """Process-wide DuckDB connection pool — one connection per file path.

    DuckDB enforces that only one connection can be open to a given file at a
    time (unless both are read-only).  This pool guarantees exactly one
    connection per canonical path, always opened in read-write mode so both
    catalog metadata writes and analytics view queries work through the same
    handle.

    Thread-safety: all public methods are protected by a reentrant lock so
    concurrent FastAPI request handlers can safely share the pool.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, duckdb.DuckDBPyConnection] = {}
        self._ref_counts: dict[str, int] = {}

    def acquire(self, db_path: str | Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        """Acquire (or reuse) a connection for *db_path*.

        Parameters
        ----------
        db_path:
            Path to DuckDB file.
        read_only:
            If True, open read-only connection (allows concurrent readers).
            If False, open read-write connection (exclusive lock).
        """
        key = str(Path(db_path).resolve())
        with self._lock:
            if key in self._connections:
                self._ref_counts[key] += 1
                return self._connections[key]

            conn = connect_with_retry(key, read_only=read_only)
            self._connections[key] = conn
            self._ref_counts[key] = 1
            logger.info("DuckDBPool: opened connection to %s (read_only=%s)", key, read_only)
            return conn

    def release(self, db_path: str | Path) -> None:
        """Release a previously-acquired connection.

        The connection is kept open until the ref-count drops to zero or
        ``close_all`` is called — closing on every release would be wasteful
        since DuckDB connections are relatively expensive to create.
        """
        key = str(Path(db_path).resolve())
        with self._lock:
            if key in self._ref_counts:
                self._ref_counts[key] -= 1

    def get(self, db_path: str | Path) -> duckdb.DuckDBPyConnection:
        """Convenience alias for ``acquire`` (ref-count is still tracked)."""
        return self.acquire(db_path)

    def close(self, db_path: str | Path) -> None:
        """Close and remove the connection for a specific path."""
        key = str(Path(db_path).resolve())
        with self._lock:
            conn = self._connections.pop(key, None)
            self._ref_counts.pop(key, None)
            if conn is not None:
                try:
                    conn.close()
                except Exception as exc:
                    logger.debug("DuckDBPool: close failed for %s: %s", key, exc)
                logger.info("DuckDBPool: closed connection to %s", key)

    def close_all(self) -> None:
        """Close every connection in the pool."""
        with self._lock:
            for key, conn in list(self._connections.items()):
                try:
                    conn.close()
                except Exception as exc:
                    logger.debug("DuckDBPool: close failed for %s: %s", key, exc)
            count = len(self._connections)
            self._connections.clear()
            self._ref_counts.clear()
            logger.info("DuckDBPool: closed %d connections", count)


# ── Module-level singleton ────────────────────────────────────────────────────

_pool: DuckDBPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> DuckDBPool:
    """Return the process-wide DuckDBPool singleton (created on first call)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = DuckDBPool()
    return _pool


def get_connection(
    db_path: str | Path = "market_data/catalog.duckdb",
    read_only: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection from the process-wide pool.

    ``read_only`` is accepted for API compatibility but ignored — all
    connections are opened in read-write mode so catalog writes and view
    queries share the same handle.
    """
    return get_pool().get(db_path)


def close_all_connections() -> None:
    """Close all pooled DuckDB connections.

    Call this during application shutdown to cleanly release all database
    connections and file locks.
    """
    pool = get_pool()
    pool.close_all()
