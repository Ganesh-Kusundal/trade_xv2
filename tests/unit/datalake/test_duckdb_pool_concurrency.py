"""Integration tests for DuckDB RW and read-only connection pools."""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb
import pytest

from datalake.core.duckdb_utils import (
    DuckDBPool,
    DuckDBReadPool,
    close_all_connections,
    duckdb_connection,
    get_connection,
    get_pool,
    get_read_pool,
)


@pytest.fixture(autouse=True)
def _reset_pools():
    """Close all pooled connections before and after each test."""
    close_all_connections()
    yield
    close_all_connections()


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_catalog.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value VARCHAR)")
    conn.execute("INSERT INTO items VALUES (1, 'alpha')")
    conn.close()
    return db_path


class TestDuckDBReadPool:
    def test_concurrent_reads(self, temp_db: Path) -> None:
        pool = DuckDBReadPool()
        errors: list[str] = []
        results: list[str] = []

        def reader() -> None:
            try:
                conn = pool.acquire(temp_db)
                row = conn.execute("SELECT value FROM items WHERE id = 1").fetchone()
                results.append(row[0])
                pool.release(temp_db, conn)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, errors
        assert len(results) == 8
        assert all(v == "alpha" for v in results)

    def test_context_manager_releases(self, temp_db: Path) -> None:
        with duckdb_connection(temp_db, read_only=True) as conn:
            assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
        pool = get_read_pool()
        assert not pool._active_connections.get(str(temp_db.resolve()), [])


class TestDuckDBPool:
    def test_ref_count_keeps_connection_open(self, temp_db: Path) -> None:
        pool = DuckDBPool()
        conn1 = pool.acquire(temp_db, read_only=False)
        conn2 = pool.acquire(temp_db, read_only=False)
        assert conn1 is conn2

        pool.release(temp_db)
        key = str(temp_db.resolve())
        assert pool._ref_counts[key] == 1
        assert key in pool._connections

        pool.release(temp_db)
        assert pool._ref_counts[key] == 0
        assert key in pool._connections

    def test_rw_write_visible_after_rw_released(self, temp_db: Path) -> None:
        rw_pool = get_pool()
        ro_pool = get_read_pool()

        rw_conn = rw_pool.acquire(temp_db, read_only=False)
        rw_conn.execute("INSERT INTO items VALUES (2, 'beta')")
        rw_pool.close(temp_db)

        ro_conn = ro_pool.acquire(temp_db)
        count = ro_conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        ro_pool.release(temp_db, ro_conn)

        assert count == 2

    def test_ro_blocked_while_rw_held(self, temp_db: Path) -> None:
        rw_pool = get_pool()
        ro_pool = get_read_pool()
        rw_pool.acquire(temp_db, read_only=False)
        with pytest.raises(duckdb.ConnectionException):
            ro_pool.acquire(temp_db)
        rw_pool.close(temp_db)


class TestGetConnectionRouting:
    def test_read_only_not_rw_pooled_handle(self, temp_db: Path) -> None:
        ro_conn = get_connection(temp_db, read_only=True)
        get_read_pool().release(temp_db, ro_conn)
        rw_conn = get_pool().acquire(temp_db, read_only=False)
        assert ro_conn is not rw_conn
        get_pool().close(temp_db)

    def test_read_write_uses_rw_pool(self, temp_db: Path) -> None:
        conn = get_connection(temp_db, read_only=False)
        pooled = get_pool().acquire(temp_db, read_only=False)
        assert conn is pooled
        get_pool().close(temp_db)


class TestConcurrentRwAndRo:
    def test_concurrent_ro_reads_without_rw_hold(self, temp_db: Path) -> None:
        ro_pool = get_read_pool()
        errors: list[str] = []

        def reader() -> None:
            try:
                ro = ro_pool.acquire(temp_db)
                ro.execute("SELECT value FROM items").fetchall()
                ro_pool.release(temp_db, ro)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
