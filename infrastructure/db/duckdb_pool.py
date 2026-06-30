"""Thread-safe DuckDB connection pool for in-memory analytics."""

from __future__ import annotations

import threading
from queue import Empty, Full, Queue

import duckdb


class DuckDBPool:
    """Simple connection pool for in-memory DuckDB connections.

    DuckDB in-memory connections (:memory:) are lightweight but still have
    non-trivial startup cost. This pool avoids creating a new connection per
    request by maintaining a small set of reusable connections.

    The pool is safe for concurrent access from multiple threads.
    """

    def __init__(self, max_size: int = 4, *, timeout: float = 5.0) -> None:
        self._max_size = max_size
        self._timeout = timeout
        self._queue: Queue[duckdb.DuckDBPyConnection] = Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._total = 0

    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(":memory:")

    def acquire(self) -> duckdb.DuckDBPyConnection:
        """Acquire a connection from the pool.

        If a connection is available it is returned immediately.  Otherwise a
        new connection is created (up to *max_size*).  If the pool is at
        capacity, the caller blocks up to *timeout* seconds.
        """
        try:
            return self._queue.get_nowait()
        except Empty:
            pass

        with self._lock:
            if self._total < self._max_size:
                self._total += 1
                return self._create_connection()

        try:
            return self._queue.get(timeout=self._timeout)
        except Empty:
            raise RuntimeError(  # noqa: B904
                f"DuckDB pool exhausted: no connection available within {self._timeout}s"
            )

    def release(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Return a connection to the pool.

        If the pool is full the connection is closed instead.
        """
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


# Module-level default pool instance
_default_pool: DuckDBPool | None = None
_default_pool_lock = threading.Lock()


def get_pool() -> DuckDBPool:
    """Return (and lazily create) the module-wide default pool."""
    global _default_pool
    if _default_pool is None:
        with _default_pool_lock:
            if _default_pool is None:
                _default_pool = DuckDBPool()
    return _default_pool


def shutdown_pool() -> None:
    """Shut down the module-wide default pool (for graceful shutdown)."""
    global _default_pool
    with _default_pool_lock:
        if _default_pool is not None:
            _default_pool.close_all()
            _default_pool = None
