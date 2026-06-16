"""Shared DuckDB connection utilities — thread-local pooling, retry, health checks.

Eliminates duplication across DataCatalog, ViewManager, and ScanStore.
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


def is_connection_healthy(conn: duckdb.DuckDBPyConnection) -> bool:
    """Validate that a DuckDB connection is still usable."""
    try:
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False


class ThreadLocalConnectionPool:
    """Thread-local connection pool for DuckDB.

    Each thread gets its own connection, lazily created on first access.
    Stale connections are automatically reconnected.

    Usage:
        pool = ThreadLocalConnectionPool("market_data/catalog.duckdb")
        conn = pool.get()  # returns thread-local connection
        pool.close_all()   # cleanup
    """

    def __init__(
        self,
        path: str | Path,
        read_only: bool = False,
        max_retry_attempts: int = 10,
    ) -> None:
        self._path = str(path)
        self._read_only = read_only
        self._max_retry_attempts = max_retry_attempts
        self._conns: dict[int, duckdb.DuckDBPyConnection] = {}
        self._lock = threading.RLock()

    def get(self) -> duckdb.DuckDBPyConnection:
        """Get or create a thread-local DuckDB connection."""
        tid = threading.current_thread().ident
        if tid is None:
            tid = 0
        with self._lock:
            conn = self._conns.get(tid)
            if conn is not None:
                if is_connection_healthy(conn):
                    return conn
                logger.warning("Stale connection for thread %d, reconnecting", tid)
                try:
                    conn.close()
                except Exception:
                    pass
                del self._conns[tid]
                conn = None
            if conn is None:
                conn = connect_with_retry(
                    self._path,
                    read_only=self._read_only,
                    max_attempts=self._max_retry_attempts,
                )
                self._conns[tid] = conn
            return conn

    def close_all(self) -> None:
        """Close all thread-local connections."""
        with self._lock:
            for conn in list(self._conns.values()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._conns.clear()

    @property
    def path(self) -> str:
        return self._path

    @property
    def read_only(self) -> bool:
        return self._read_only
