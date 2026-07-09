"""Tests for ConnectionPoolManager (Phase 3).

Covers:
- Thread-safe session creation (double-checked locking)
- Session reuse
- close_all lifecycle
- Context manager support
- get_stats
- Singleton get_connection_pool / reset_connection_pool
- Concurrent access from multiple threads
- Post-close behavior
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import pytest
import requests

from tradex.runtime.connection_pool import (
    ConnectionPoolManager,
    get_connection_pool,
    reset_connection_pool,
)

# ---------------------------------------------------------------------------
# Basic creation and configuration tests
# ---------------------------------------------------------------------------


class TestConnectionPoolCreation:
    def test_default_configuration(self) -> None:
        pool = ConnectionPoolManager()
        stats = pool.get_stats()
        assert stats["pool_connections"] == 50
        assert stats["pool_maxsize"] == 100
        assert stats["max_retries"] == 3
        assert stats["session_count"] == 0
        assert stats["is_closed"] is False

    def test_custom_configuration(self) -> None:
        pool = ConnectionPoolManager(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=5,
        )
        stats = pool.get_stats()
        assert stats["pool_connections"] == 10
        assert stats["pool_maxsize"] == 20
        assert stats["max_retries"] == 5


# ---------------------------------------------------------------------------
# Session creation and reuse tests
# ---------------------------------------------------------------------------


class TestSessionManagement:
    def test_get_session_creates_session(self) -> None:
        pool = ConnectionPoolManager()
        session = pool.get_session("upstox")
        assert isinstance(session, requests.Session)
        assert pool.get_stats()["session_count"] == 1

    def test_get_session_reuses_existing(self) -> None:
        pool = ConnectionPoolManager()
        s1 = pool.get_session("upstox")
        s2 = pool.get_session("upstox")
        assert s1 is s2  # Same object

    def test_different_brokers_get_different_sessions(self) -> None:
        pool = ConnectionPoolManager()
        s1 = pool.get_session("upstox")
        s2 = pool.get_session("dhan")
        assert s1 is not s2
        assert pool.get_stats()["session_count"] == 2

    def test_session_has_http_adapter(self) -> None:
        pool = ConnectionPoolManager()
        session = pool.get_session("test")
        # Verify adapters are mounted
        assert "https://" in session.adapters
        assert "http://" in session.adapters

    def test_session_has_default_headers(self) -> None:
        pool = ConnectionPoolManager()
        session = pool.get_session("test")
        assert session.headers.get("Accept") == "application/json"
        assert session.headers.get("Content-Type") == "application/json"

    def test_broker_keys_tracked(self) -> None:
        pool = ConnectionPoolManager()
        pool.get_session("alpha")
        pool.get_session("beta")
        stats = pool.get_stats()
        assert set(stats["broker_keys"]) == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_session_creation_same_key(self) -> None:
        """Multiple threads requesting the same broker key should get the same session."""
        pool = ConnectionPoolManager()
        results: list[requests.Session] = []
        lock = threading.Lock()

        def get_and_store() -> None:
            session = pool.get_session("concurrent")
            with lock:
                results.append(session)

        threads = [threading.Thread(target=get_and_store) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should have received the same session
        assert len(results) == 20
        assert all(s is results[0] for s in results)
        assert pool.get_stats()["session_count"] == 1

    def test_concurrent_session_creation_different_keys(self) -> None:
        """Multiple threads requesting different keys should not interfere."""
        pool = ConnectionPoolManager()
        results: dict[str, requests.Session] = {}
        lock = threading.Lock()

        def get_and_store(key: str) -> None:
            session = pool.get_session(key)
            with lock:
                results[key] = session

        keys = [f"broker_{i}" for i in range(10)]
        threads = [threading.Thread(target=get_and_store, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert pool.get_stats()["session_count"] == 10

    def test_concurrent_get_session_with_thread_pool(self) -> None:
        """ThreadPoolExecutor based concurrent access."""
        pool = ConnectionPoolManager()
        futures_results: list[requests.Session] = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            futs = [executor.submit(pool.get_session, f"tp_broker_{i}") for i in range(16)]
            for f in as_completed(futs):
                futures_results.append(f.result())

        assert len(futures_results) == 16
        # Unique sessions count
        unique = {id(s) for s in futures_results}
        assert len(unique) == 16


# ---------------------------------------------------------------------------
# Close lifecycle tests
# ---------------------------------------------------------------------------


class TestCloseLifecycle:
    def test_close_all_closes_sessions(self) -> None:
        pool = ConnectionPoolManager()
        pool.get_session("upstox")
        pool.get_session("dhan")
        pool.close_all()

        stats = pool.get_stats()
        assert stats["session_count"] == 0
        assert stats["is_closed"] is True

    def test_close_all_idempotent(self) -> None:
        pool = ConnectionPoolManager()
        pool.get_session("test")
        pool.close_all()
        pool.close_all()  # Should not raise

    def test_get_session_after_close_raises(self) -> None:
        pool = ConnectionPoolManager()
        pool.close_all()
        with pytest.raises(RuntimeError, match="closed"):
            pool.get_session("upstox")

    def test_close_with_session_close_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """If a session.close() raises, it should be logged but not propagate."""
        pool = ConnectionPoolManager()
        mock_session = pool.get_session("bad")

        with patch.object(mock_session, "close", side_effect=OSError("bad close")):
            pool.close_all()

        assert any("Error closing session" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Context manager tests
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_context_manager_closes_on_exit(self) -> None:
        with ConnectionPoolManager() as pool:
            pool.get_session("ctx")
            assert pool.get_stats()["is_closed"] is False

        assert pool.get_stats()["is_closed"] is True

    def test_context_manager_closes_on_exception(self) -> None:
        pool_ref = None
        try:
            with ConnectionPoolManager() as pool:
                pool_ref = pool
                pool.get_session("ctx")
                raise ValueError("context error")
        except ValueError:
            pass

        assert pool_ref is not None
        assert pool_ref.get_stats()["is_closed"] is True


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestSingleton:
    def teardown_method(self) -> None:
        reset_connection_pool()

    def test_get_connection_pool_returns_instance(self) -> None:
        pool = get_connection_pool()
        assert isinstance(pool, ConnectionPoolManager)

    def test_get_connection_pool_is_singleton(self) -> None:
        p1 = get_connection_pool()
        p2 = get_connection_pool()
        assert p1 is p2

    def test_reset_connection_pool_clears_singleton(self) -> None:
        p1 = get_connection_pool()
        reset_connection_pool()
        p2 = get_connection_pool()
        assert p1 is not p2

    def test_reset_closes_previous_pool(self) -> None:
        p1 = get_connection_pool()
        p1.get_session("test")
        reset_connection_pool()
        # Old pool should be closed
        assert p1.get_stats()["is_closed"] is True

    def test_singleton_after_reset_can_create_sessions(self) -> None:
        get_connection_pool()
        reset_connection_pool()
        pool = get_connection_pool()
        session = pool.get_session("after_reset")
        assert isinstance(session, requests.Session)


# ---------------------------------------------------------------------------
# get_stats tests
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_initial_stats(self) -> None:
        pool = ConnectionPoolManager()
        stats = pool.get_stats()
        assert stats["session_count"] == 0
        assert stats["broker_keys"] == []
        assert stats["is_closed"] is False

    def test_stats_after_sessions(self) -> None:
        pool = ConnectionPoolManager()
        pool.get_session("a")
        pool.get_session("b")
        stats = pool.get_stats()
        assert stats["session_count"] == 2
        assert set(stats["broker_keys"]) == {"a", "b"}

    def test_stats_after_close(self) -> None:
        pool = ConnectionPoolManager()
        pool.get_session("x")
        pool.close_all()
        stats = pool.get_stats()
        assert stats["session_count"] == 0
        assert stats["is_closed"] is True
