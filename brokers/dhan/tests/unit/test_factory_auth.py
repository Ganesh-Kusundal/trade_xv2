"""Unit tests for BrokerFactory AuthManager integration."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock

from brokers.common.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState


def _make_jwt(payload: dict) -> str:
    """Build a minimal JWT-like string with the given payload."""
    header = base64.b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = base64.b64encode(b"fakesignature").decode().rstrip("=")
    return f"{header}.{body}.{signature}"


class TestJsonTokenStateStore:
    def test_save_and_load(self, tmp_path):
        from datetime import datetime
        store = JsonTokenStateStore(tmp_path / "token.json")
        state = TokenState(
            access_token="test_token",
            source=TokenSource.TOTP,
            expires_at=datetime.now().replace(hour=23, minute=59),
        )
        store.save(state)
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "test_token"

    def test_load_nonexistent(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "nonexistent.json")
        assert store.load() is None

    def test_save_none_deletes_file(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        state = TokenState(access_token="test", source=TokenSource.TOTP)
        store.save(state)
        assert (tmp_path / "token.json").exists()
        store.save(None)
        assert not (tmp_path / "token.json").exists()

    def test_roundtrip_with_timestamps(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        from datetime import datetime
        now = datetime.now()
        state = TokenState(
            access_token="roundtrip_test",
            source=TokenSource.TOTP,
            issued_at=now,
            expires_at=now,
        )
        store.save(state)
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "roundtrip_test"
        assert loaded.issued_at is not None
        assert loaded.expires_at is not None


class TestAuthManagerIntegration:
    def test_acquire_from_store(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        valid_token = _make_jwt({"exp": int(time.time()) + 7200})
        store.save(TokenState(access_token=valid_token, source=TokenSource.TOTP))

        auth = AuthManager(
            client_id="test_client",
            token_store=store,
            token_source=TokenSource.TOTP,
        )
        state = auth.acquire()
        assert state is not None
        assert state.access_token == valid_token

    def test_acquire_via_callback(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        fresh_token = _make_jwt({"exp": int(time.time()) + 7200})

        auth = AuthManager(
            client_id="test_client",
            token_store=store,
            token_source=TokenSource.TOTP,
            on_acquire=lambda: fresh_token,
        )
        state = auth.acquire()
        assert state is not None
        assert state.access_token == fresh_token
        # Should have persisted to store
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == fresh_token

    def test_ensure_valid_refreshes_when_needed(self, tmp_path):
        from datetime import datetime, timedelta
        store = JsonTokenStateStore(tmp_path / "token.json")
        # Store a token expiring in 4 minutes (within 5-min buffer)
        # But total lifetime must be > buffer for normal refresh logic
        issued_at = datetime.now() - timedelta(hours=23, minutes=55)
        expires_at = datetime.now() + timedelta(minutes=4)
        store.save(TokenState(
            access_token="expiring_token",
            source=TokenSource.TOTP,
            issued_at=issued_at,
            expires_at=expires_at,
        ))

        fresh_token = _make_jwt({"exp": int(time.time()) + 7200})
        auth = AuthManager(
            client_id="test_client",
            token_store=store,
            token_source=TokenSource.TOTP,
            on_refresh=lambda: fresh_token,
        )
        auth.acquire()

        # ensure_valid should trigger refresh because token is within buffer
        result = auth.ensure_valid(buffer_seconds=300)
        assert result is True
        assert auth.state.access_token == fresh_token

    def test_revoke_clears_store(self, tmp_path):
        store = JsonTokenStateStore(tmp_path / "token.json")
        auth = AuthManager(
            client_id="test_client",
            token_store=store,
            token_source=TokenSource.TOTP,
            on_acquire=lambda: _make_jwt({"exp": int(time.time()) + 7200}),
        )
        auth.acquire()
        assert store.load() is not None
        auth.revoke()
        assert store.load() is None

    def test_on_refresh_callback(self, tmp_path):
        callback = MagicMock()
        auth = AuthManager(
            client_id="test_client",
            token_source=TokenSource.TOTP,
            on_acquire=lambda: _make_jwt({"exp": int(time.time()) + 7200}),
        )
        auth.on_refresh(callback)
        auth.acquire()
        callback.assert_called_once()
