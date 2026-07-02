"""Shared DuckDB connection utilities — process-wide connection pools.

Provides:
- ``connect_with_retry`` for handling DuckDB's single-writer lock
- ``DuckDBPool`` for read-write connection reuse (one RW conn per file)
- ``DuckDBReadPool`` for concurrent read-only connections (fresh conn per acquire)
- ``InMemoryDuckDBPool`` for reusable in-memory connections (queue-based)
- ``get_pool`` / ``get_read_pool`` / ``get_memory_pool`` / ``get_connection`` / ``duckdb_connection``
- ``close_all_connections`` for clean shutdown

Used by DataCatalog, ViewManager, ScanStore, and API endpoints.

RW and RO pools are separate: catalog writes and materialization use
``DuckDBPool``; API read handlers use ``DuckDBReadPool`` for concurrency.
In-memory analytics use ``InMemoryDuckDBPool`` for connection reuse.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Full, Queue

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

    Max connections per path is capped to prevent FD exhaustion under
    high concurrency. Default cap: 32 per path.

    Usage:
        pool = DuckDBReadPool()
        conn = pool.acquire("market_data/catalog.duckdb")
        try:
            result = conn.execute("SELECT ...").fetchdf()
        finally:
            pool.release("market_data/catalog.duckdb")
    """

    MAX_PER_PATH = 32

    def __init__(self, max_per_path: int = MAX_PER_PATH) -> None:
        self._lock = threading.RLock()
        self._active_connections: dict[str, list[duckdb.DuckDBPyConnection]] = {}
        self._max_per_path = max_per_path

    def acquire(self, db_path: str | Path) -> duckdb.DuckDBPyConnection:
        """Create a new read-only connection for concurrent reads.

        Raises RuntimeError if max connections per path is reached.
        """
        key = str(Path(db_path).resolve())
        with self._lock:
            current = len(self._active_connections.get(key, []))
            if current >= self._max_per_path:
                raise RuntimeError(
                    f"DuckDBReadPool: max connections ({self._max_per_path}) "
                    f"reached for {key}. Release a connection first."
                )
        conn = connect_with_retry(key, read_only=True)
        with self._lock:
            if key not in self._active_connections:
                self._active_connections[key] = []
            self._active_connections[key].append(conn)
        logger.debug("DuckDBReadPool: created read-only connection to %s (%d/%d)",
                      key, current + 1, self._max_per_path)
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
            if self._active_connections.get(key):
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


# ── Module-level singletons ───────────────────────────────────────────────────

_pool: DuckDBPool | None = None
_read_pool: DuckDBReadPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> DuckDBPool:
    """Return the process-wide DuckDBPool singleton (created on first call)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = DuckDBPool()
    return _pool


def get_read_pool() -> DuckDBReadPool:
    """Return the process-wide DuckDBReadPool singleton (created on first call)."""
    global _read_pool
    if _read_pool is None:
        with _pool_lock:
            if _read_pool is None:
                _read_pool = DuckDBReadPool()
    return _read_pool


def get_connection(
    db_path: str | Path = "market_data/catalog.duckdb",
    read_only: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection from the appropriate pool.

    Read-only requests use ``DuckDBReadPool`` (caller must ``release`` via
    ``duckdb_connection`` context manager). Read-write requests use
    ``DuckDBPool``.
    """
    path = Path(db_path)
    if read_only:
        return get_read_pool().acquire(path)
    return get_pool().acquire(path, read_only=False)


@contextmanager
def duckdb_connection(
    db_path: str | Path,
    read_only: bool = True,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Acquire and release a DuckDB connection safely.

    Example::

        with duckdb_connection("market_data/catalog.duckdb", read_only=True) as conn:
            rows = conn.execute("SELECT 1").fetchall()
    """
    path = Path(db_path)
    if read_only:
        pool = get_read_pool()
        conn = pool.acquire(path)
        try:
            yield conn
        finally:
            pool.release(path, conn)
    else:
        pool = get_pool()
        conn = pool.acquire(path, read_only=False)
        try:
            yield conn
        finally:
            pool.release(path)


def close_all_connections() -> None:
    """Close all pooled DuckDB connections (RW, RO, and in-memory).

    Call this during application shutdown to cleanly release all database
    connections and file locks.
    """
    get_read_pool().close_all()
    get_pool().close_all()
    get_memory_pool().close_all()


class InMemoryDuckDBPool:
    """Queue-based pool for in-memory DuckDB connections.

    DuckDB in-memory connections (:memory:) are lightweight but still have
    non-trivial startup cost. This pool avoids creating a new connection per
    request by maintaining a small set of reusable connections.

    Thread-safe for concurrent access from multiple threads.
    """

    def __init__(self, max_size: int = 4, *, timeout: float = 5.0) -> None:
        self._max_size = max_size
        self._timeout = timeout
        self._queue: Queue[duckdb.DuckDBPyConnection] = Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._total = 0

    def acquire(self) -> duckdb.DuckDBPyConnection:
        """Acquire a connection from the pool.

        If a connection is available it is returned immediately. Otherwise a
        new connection is created (up to *max_size*). If the pool is at
        capacity, the caller blocks up to *timeout* seconds.
        """
        try:
            return self._queue.get_nowait()
        except Empty:
            pass

        with self._lock:
            if self._total < self._max_size:
                self._total += 1
                return duckdb.connect(":memory:")

        try:
            return self._queue.get(timeout=self._timeout)
        except Empty:
            raise RuntimeError(
                f"InMemoryDuckDBPool exhausted: no connection available within {self._timeout}s"
            )

    def release(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Return a connection to the pool. If the pool is full, close instead."""
        try:
            self._queue.put_nowait(conn)
        except Full:
            conn.close()
            with self._lock:
                self._total -= 1

    def close_all(self) -> None:
        """Close every connection in the pool."""
        while not self._queue.empty():
            try:
                conn = self._queue.get_nowait()
                conn.close()
            except Empty:
                break
        with self._lock:
            self._total = 0

    @property
    def size(self) -> int:
        """Number of connections currently managed by the pool."""
        return self._total


_memory_pool: InMemoryDuckDBPool | None = None
_memory_pool_lock = threading.Lock()


def get_memory_pool() -> InMemoryDuckDBPool:
    """Return the process-wide InMemoryDuckDBPool singleton (created on first call)."""
    global _memory_pool
    if _memory_pool is None:
        with _memory_pool_lock:
            if _memory_pool is None:
                _memory_pool = InMemoryDuckDBPool()
    return _memory_pool


def reset_memory_pool() -> None:
    """Close and reset the process-wide InMemoryDuckDBPool singleton.

    Thread-safe: acquires the pool lock before mutating the singleton.
    After this call, the next ``get_memory_pool()`` creates a fresh pool.
    """
    global _memory_pool
    with _memory_pool_lock:
        if _memory_pool is not None:
            _memory_pool.close_all()
            _memory_pool = None
