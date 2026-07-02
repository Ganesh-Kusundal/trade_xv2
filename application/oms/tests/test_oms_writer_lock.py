"""Tests for OMS SQLite single-writer lock."""

from __future__ import annotations

import pytest

from infrastructure.persistence.sqlite_order_store import OmsWriterLockError, SqliteOrderStore


@pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="fcntl writer lock is Unix-only",
)
def test_second_store_raises_when_lock_held(tmp_path) -> None:
    db = tmp_path / "orders.sqlite"
    store1 = SqliteOrderStore(db, require_single_writer=True)
    assert store1.writer_lock_held()

    with pytest.raises(OmsWriterLockError):
        SqliteOrderStore(db, require_single_writer=True)

    store1.close()

    store2 = SqliteOrderStore(db, require_single_writer=True)
    store2.close()


def test_writer_lock_skipped_when_disabled(tmp_path) -> None:
    db = tmp_path / "orders.sqlite"
    store1 = SqliteOrderStore(db, require_single_writer=False)
    store2 = SqliteOrderStore(db, require_single_writer=False)
    store1.close()
    store2.close()
