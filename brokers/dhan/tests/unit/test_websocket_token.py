"""Tests for DhanTokenManager — token refresh and validation."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

import pytest

from brokers.dhan.ws_token_manager import DhanTokenManager


class TestTokenManagerInit:
    """Verify token manager initialization."""

    def test_init_static_token(self):
        """Must store static token."""
        mgr = DhanTokenManager(client_id="TEST_CLIENT", access_token="TEST_TOKEN")
        assert mgr.client_id == "TEST_CLIENT"
        assert mgr.get_token() == "TEST_TOKEN"

    def test_init_with_token_fn(self):
        """Must prefer token_fn over static token."""
        mgr = DhanTokenManager(
            client_id="TEST_CLIENT",
            access_token="STATIC_TOKEN",
            access_token_fn=lambda: "DYNAMIC_TOKEN",
        )
        assert mgr.get_token() == "DYNAMIC_TOKEN"

    def test_init_no_token(self):
        """Must handle missing token gracefully."""
        mgr = DhanTokenManager(client_id="TEST_CLIENT")
        assert mgr.get_token() == ""


class TestGetToken:
    """Verify token retrieval behavior."""

    def test_get_token_static(self):
        """Must return static token when no fn provided."""
        mgr = DhanTokenManager(client_id="C", access_token="TOKEN123")
        assert mgr.get_token() == "TOKEN123"

    def test_get_token_from_fn(self):
        """Must call fn and return result."""
        call_count = [0]
        def token_fn():
            call_count[0] += 1
            return "FRESH_TOKEN"

        mgr = DhanTokenManager(client_id="C", access_token_fn=token_fn)
        assert mgr.get_token() == "FRESH_TOKEN"
        assert call_count[0] == 1

    def test_get_token_fn_exception_fallback(self, caplog):
        """Must fall back to static token when fn raises."""
        def bad_fn():
            raise RuntimeError("token service unavailable")

        mgr = DhanTokenManager(
            client_id="C",
            access_token="FALLBACK_TOKEN",
            access_token_fn=bad_fn,
        )
        token = mgr.get_token()
        assert token == "FALLBACK_TOKEN"

    def test_get_token_fn_exception_no_static(self, caplog):
        """Must return empty string when fn raises and no static token."""
        def bad_fn():
            raise RuntimeError("token service unavailable")

        mgr = DhanTokenManager(client_id="C", access_token_fn=bad_fn)
        assert mgr.get_token() == ""


class TestUpdateToken:
    """Verify token update behavior."""

    def test_update_static_token(self):
        """Must update static token."""
        mgr = DhanTokenManager(client_id="C", access_token="OLD_TOKEN")
        mgr.update_token("NEW_TOKEN")
        assert mgr.get_token() == "NEW_TOKEN"

    def test_update_does_not_affect_fn(self):
        """Must not affect token_fn behavior."""
        mgr = DhanTokenManager(
            client_id="C",
            access_token="STATIC",
            access_token_fn=lambda: "DYNAMIC",
        )
        mgr.update_token("UPDATED_STATIC")
        assert mgr.get_token() == "DYNAMIC"

    def test_update_then_disable_fn(self):
        """After fn removed, updated static token is used."""
        mgr = DhanTokenManager(
            client_id="C",
            access_token="OLD_STATIC",
            access_token_fn=lambda: "DYNAMIC",
        )
        mgr.update_token("NEW_STATIC")
        assert mgr.get_token() == "DYNAMIC"
        mgr._access_token_fn = None
        assert mgr.get_token() == "NEW_STATIC"


class TestTokenValidation:
    """Verify token validation logic."""

    def test_valid_token(self):
        """Non-empty token is valid."""
        mgr = DhanTokenManager(client_id="C", access_token="VALID_TOKEN")
        assert mgr.is_token_valid() is True

    def test_empty_token_invalid(self):
        """Empty token is invalid."""
        mgr = DhanTokenManager(client_id="C")
        assert mgr.is_token_valid() is False

    def test_whitespace_token_invalid(self):
        """Whitespace-only token is invalid."""
        mgr = DhanTokenManager(client_id="C", access_token="   ")
        assert mgr.is_token_valid() is False

    def test_none_token_invalid(self):
        """None token is invalid."""
        mgr = DhanTokenManager(client_id="C", access_token=None)
        assert mgr.is_token_valid() is False


class TestClientID:
    """Verify client_id handling."""

    def test_client_id_stored(self):
        """Must store and return client_id."""
        mgr = DhanTokenManager(client_id="CLIENT_123")
        assert mgr.client_id == "CLIENT_123"

    def test_client_id_immutable(self):
        """client_id should not change after init."""
        mgr = DhanTokenManager(client_id="CLIENT_123")
        mgr.update_token("NEW_TOKEN")
        assert mgr.client_id == "CLIENT_123"


class TestTokenManagerThreadSafety:
    """Verify thread safety of token manager."""

    def test_concurrent_get_token(self):
        """Concurrent get_token calls must not deadlock or corrupt state."""
        import threading

        mgr = DhanTokenManager(client_id="C", access_token="TOKEN")
        results = []
        errors = []

        def get_token_thread():
            try:
                for _ in range(100):
                    token = mgr.get_token()
                    results.append(token == "TOKEN")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_token_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0
        assert all(results)

    def test_concurrent_update_and_get(self):
        """Concurrent update and get must be consistent."""
        import threading

        mgr = DhanTokenManager(client_id="C", access_token="INITIAL")
        final_tokens = set()
        errors = []

        def updater(n):
            try:
                for i in range(10):
                    mgr.update_token(f"TOKEN_{n}_{i}")
            except Exception as e:
                errors.append(e)

        def getter():
            try:
                for _ in range(50):
                    token = mgr.get_token()
                    if token:
                        final_tokens.add(token)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=updater, args=(i,)))
        for _ in range(5):
            threads.append(threading.Thread(target=getter))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0
        assert len(final_tokens) >= 1  # At least saw some token values
