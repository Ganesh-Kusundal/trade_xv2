"""Tests for DuckDB lock-conflict retry + SQLite journal concurrency.

Two concurrency strategies are now in play:

* **DuckDB paths** (scan_store, analytics views) use a shared
  ``connect_with_retry`` helper from ``datalake.duckdb_utils`` that retries
  with exponential backoff when a writer holds the file.
* **TradeJournal** is now SQLite-backed with WAL mode, so concurrent readers
  + a single writer coexist without explicit locking. Tested here.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from datalake.duckdb_utils import connect_with_retry
from datalake.journal import TradeJournal


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    path = tmp_path / "retry.duckdb"
    conn = duckdb.connect(str(path), read_only=False)
    conn.execute("CREATE TABLE t (x INT)")
    conn.close()
    return path


class TestDuckDBRetryHelper:
    """Direct unit tests for the shared retry helper."""

    def test_succeeds_on_unlocked_file(self, tmp_db: Path) -> None:
        conn = connect_with_retry(str(tmp_db), read_only=True, max_attempts=3)
        assert conn is not None
        conn.close()

    def test_retries_then_succeeds_when_writer_releases(self, tmp_db: Path) -> None:
        # DuckDB doesn't allow mixed read_only configs in one process, so the
        # holder must be a subprocess. The retry helper's purpose is exactly
        # this cross-process lock scenario.
        holder = subprocess.Popen(
            [sys.executable, "-c", f"""
import time
import duckdb
c = duckdb.connect(r"{tmp_db}", read_only=False)
c.execute("SELECT 1")
time.sleep(0.4)
c.close()
"""],
        )
        time.sleep(0.1)  # let holder grab the lock

        try:
            t0 = time.time()
            conn = connect_with_retry(str(tmp_db), read_only=True, max_attempts=10)
            elapsed = time.time() - t0
            assert conn is not None
            conn.close()
            # Should wait roughly until holder releases (~0.4s) — well under budget
            assert elapsed < 3.0, f"retry took {elapsed:.2f}s, expected <3s"
        finally:
            holder.wait()

    def test_non_lock_error_propagates(self, tmp_db: Path) -> None:
        with pytest.raises(duckdb.IOException):
            connect_with_retry("/nonexistent/path/db.duckdb", read_only=True, max_attempts=3)

    def test_dual_read_only_connections(self, tmp_db: Path) -> None:
        a = duckdb.connect(str(tmp_db), read_only=True)
        b = duckdb.connect(str(tmp_db), read_only=True)
        assert a.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
        assert b.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
        a.close()
        b.close()


class TestSQLiteJournalConcurrency:
    """The SQLite-backed TradeJournal must support concurrent readers + a writer
    (WAL mode). No retry needed — SQLite's WAL gives us this for free."""

    def test_concurrent_readers(self, tmp_path: Path) -> None:
        path = tmp_path / "test_journal.sqlite"
        writer = TradeJournal(catalog_path=path)
        try:
            writer.record_trade("T1", "RELIANCE", "momentum",
                                entry_time=datetime.now(), entry_price=2500.0,
                                quantity=10, side="BUY")
        finally:
            writer.close()

        # Two readers concurrently — should not block or error
        r1 = TradeJournal(catalog_path=path, read_only=True)
        r2 = TradeJournal(catalog_path=path, read_only=True)
        try:
            assert r1.get_trades(limit=10)[0]["trade_id"] == "T1"
            assert r2.get_trades(limit=10)[0]["trade_id"] == "T1"
        finally:
            r1.close()
            r2.close()

    def test_reader_during_writer(self, tmp_path: Path) -> None:
        """Reader stays open while writer commits — neither should error.

        SQLite WAL mode gives readers a consistent view within a single
        transaction, but our helper uses autocommit (one transaction per
        execute). So we verify the simpler invariant: reader + writer
        coexist without blocking or erroring.
        """
        path = tmp_path / "test_journal.sqlite"
        w = TradeJournal(catalog_path=path)
        w.record_trade("T1", "RELIANCE", "momentum",
                       entry_time=datetime.now(), entry_price=2500.0,
                       quantity=10, side="BUY")
        w.close()

        r = TradeJournal(catalog_path=path, read_only=True)
        try:
            assert len(r.get_trades()) == 1

            # Open a long-lived writer that holds the connection open
            w2 = TradeJournal(catalog_path=path)
            try:
                # Multiple reads while writer is open — should not error
                for _ in range(3):
                    trades = r.get_trades()
                    assert trades[0]["trade_id"] == "T1"
                w2.record_trade("T2", "TCS", "value",
                                entry_time=datetime.now(), entry_price=3500.0,
                                quantity=5, side="BUY")
            finally:
                w2.close()
        finally:
            r.close()

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        """Sanity check: writer connection must set journal_mode=WAL."""
        path = tmp_path / "test_journal.sqlite"
        w = TradeJournal(catalog_path=path)
        try:
            conn = w._ensure_conn()
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal", f"expected WAL, got {mode}"
        finally:
            w.close()
