"""TDD tests for auth module — TokenSource, TokenState, TokenStateStore, AuthManager.

Inspired by Trade_J's auth architecture (TokenLifecycleService, TokenStateStore).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from brokers.common.core.auth import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
)


class TestTokenSource:
    def test_values(self):
        assert TokenSource.STATIC.value == "STATIC"
        assert TokenSource.TOTP.value == "TOTP"
        assert TokenSource.OAUTH.value == "OAUTH"
        assert TokenSource.INTERACTIVE.value == "INTERACTIVE"


class TestTokenState:
    def test_default_state(self):
        state = TokenState()
        assert state.access_token == ""
        assert state.refresh_token is None
        assert state.source == TokenSource.STATIC

    def test_is_valid_with_token(self):
        future = datetime.now() + timedelta(hours=1)
        state = TokenState(access_token="abc123", expires_at=future)
        assert state.is_valid() is True

    def test_is_valid_expired(self):
        past = datetime.now() - timedelta(hours=1)
        state = TokenState(access_token="expired", expires_at=past)
        assert state.is_valid() is False

    def test_is_valid_no_token(self):
        state = TokenState()
        assert state.is_valid() is False

    def test_is_valid_with_clock_skew(self):
        # Within 30s clock skew should still be valid
        just_past = datetime.now() - timedelta(seconds=15)
        state = TokenState(access_token="ok", expires_at=just_past)
        assert state.is_valid() is True

    def test_remaining_seconds(self):
        future = datetime.now() + timedelta(hours=2)
        state = TokenState(access_token="tok", expires_at=future)
        remaining = state.remaining_seconds()
        assert 7100 < remaining < 7300  # ~7200 seconds (2 hours)

    def test_remaining_seconds_expired(self):
        past = datetime.now() - timedelta(minutes=5)
        state = TokenState(access_token="tok", expires_at=past)
        assert state.remaining_seconds() < 0

    def test_remaining_seconds_no_expiry(self):
        state = TokenState(access_token="tok")
        assert state.remaining_seconds() == 0.0

    def test_refresh_recommended(self):
        # Token expiring in 2 minutes — refresh recommended with 5 min buffer
        near_future = datetime.now() + timedelta(minutes=2)
        state = TokenState(
            access_token="tok",
            issued_at=datetime.now() - timedelta(hours=1),
            expires_at=near_future,
        )
        assert state.refresh_recommended(buffer_seconds=300) is True

    def test_refresh_not_recommended(self):
        far_future = datetime.now() + timedelta(hours=24)
        state = TokenState(
            access_token="tok",
            issued_at=datetime.now(),
            expires_at=far_future,
        )
        assert state.refresh_recommended(buffer_seconds=300) is False

    def test_refresh_short_lived_token_safety(self):
        """Short-lived tokens (< buffer) should not be proactively refreshed."""
        near_future = datetime.now() + timedelta(seconds=30)
        state = TokenState(
            access_token="tok",
            issued_at=datetime.now(),
            expires_at=near_future,
        )
        # Token lifetime is 30s, buffer is 300s — safety kicks in
        assert state.refresh_recommended(buffer_seconds=300) is False


class TestTokenStateStoreInterface:
    def test_abstract_methods(self):
        """All stores must implement load and save."""
        for method in ["load", "save"]:
            assert hasattr(TokenStateStore, method)
            assert hasattr(TokenStateStore.__dict__[method], "__isabstractmethod__")

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            TokenStateStore()  # type: ignore


class TestEnvTokenStateStore:
    def test_load_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("TRADEJ_TOKEN_ACCESS", raising=False)
        store = EnvTokenStateStore()
        assert store.load() is None

    def test_load_from_env(self, monkeypatch):
        monkeypatch.setenv("TRADEJ_TOKEN_ACCESS", "test_access_123")
        monkeypatch.setenv("TRADEJ_TOKEN_REFRESH", "test_refresh_456")
        monkeypatch.setenv("TRADEJ_TOKEN_EXPIRES_AT", "2026-12-31T23:59:59")
        store = EnvTokenStateStore()
        state = store.load()
        assert state is not None
        assert state.access_token == "test_access_123"
        assert state.refresh_token == "test_refresh_456"

    def test_save_caches_in_memory(self, monkeypatch):
        monkeypatch.delenv("TRADEJ_TOKEN_ACCESS", raising=False)
        store = EnvTokenStateStore()
        state = TokenState(access_token="cached_token")
        store.save(state)
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "cached_token"

    def test_save_none_clears_cache(self):
        store = EnvTokenStateStore()
        store.save(TokenState(access_token="temp"))
        store.save(None)
        assert store.load() is None


class TestJsonTokenStateStore:
    @pytest.fixture
    def tmp_path(self, tmp_path):
        return tmp_path / "token.json"

    def test_load_none_when_missing(self, tmp_path):
        store = JsonTokenStateStore(tmp_path)
        assert store.load() is None

    def test_save_and_load(self, tmp_path):
        store = JsonTokenStateStore(tmp_path)
        state = TokenState(
            access_token="json_token",
            refresh_token="json_refresh",
            source=TokenSource.OAUTH,
        )
        store.save(state)
        assert tmp_path.exists()
        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "json_token"
        assert loaded.refresh_token == "json_refresh"
        assert loaded.source == TokenSource.OAUTH

    def test_save_none_clears_file(self, tmp_path):
        store = JsonTokenStateStore(tmp_path)
        store.save(TokenState(access_token="temp"))
        assert tmp_path.exists()
        store.save(None)
        assert not tmp_path.exists()

    def test_load_invalid_json(self, tmp_path):
        tmp_path.write_text("{invalid json}")
        store = JsonTokenStateStore(tmp_path)
        assert store.load() is None


class TestAuthManager:
    def test_not_authenticated_by_default(self):
        auth = AuthManager(client_id="test")
        assert auth.is_authenticated is False
        assert auth.state is None

    def test_acquire_from_store(self):
        store = MagicMock(spec=TokenStateStore)
        future = datetime.now() + timedelta(hours=1)
        store.load.return_value = TokenState(
            access_token="stored_token",
            expires_at=future,
        )
        auth = AuthManager(client_id="test", token_store=store)
        state = auth.acquire()
        assert state is not None
        assert state.access_token == "stored_token"
        assert auth.is_authenticated is True

    def test_acquire_from_callback_when_store_empty(self):
        store = MagicMock(spec=TokenStateStore)
        store.load.return_value = None
        auth = AuthManager(
            client_id="test",
            token_store=store,
            on_acquire=lambda: "callback_token",
        )
        state = auth.acquire()
        assert state is not None
        assert state.access_token == "callback_token"
        store.save.assert_called_once()

    def test_acquire_returns_none_when_no_source(self):
        auth = AuthManager(client_id="test")
        state = auth.acquire()
        assert state is None

    def test_ensure_valid_does_nothing_for_valid_token(self):
        future = datetime.now() + timedelta(hours=24)
        auth = AuthManager(client_id="test")
        auth._state = TokenState(access_token="valid", expires_at=future)
        assert auth.ensure_valid() is True

    def test_ensure_valid_refreshes_when_expired(self):
        past = datetime.now() - timedelta(hours=1)
        called = [False]

        def refresh():
            called[0] = True
            return "fresh_token"

        auth = AuthManager(client_id="test", on_refresh=refresh, on_acquire=refresh)
        auth._state = TokenState(
            access_token="expired",
            expires_at=past,
        )
        assert auth.ensure_valid() is True
        assert called[0] is True
        assert auth.state.access_token == "fresh_token"

    def test_revoke_clears_state(self):
        store = MagicMock(spec=TokenStateStore)
        auth = AuthManager(client_id="test", token_store=store)
        auth._state = TokenState(access_token="tok")
        auth.revoke()
        assert auth.state is None
        store.save.assert_called_with(None)

    def test_on_expiry_callback_fired(self):
        auth = AuthManager(client_id="test")
        calls = []
        auth.on_expiry(lambda: calls.append("expired"))
        auth.revoke()
        assert len(calls) == 1

    def test_on_refresh_callback_fired(self):
        store = MagicMock(spec=TokenStateStore)
        store.load.return_value = None
        auth = AuthManager(
            client_id="test",
            token_store=store,
            on_acquire=lambda: "new_token",
        )
        calls = []
        auth.on_refresh(lambda: calls.append("refreshed"))
        auth.acquire()
        assert len(calls) == 1

    def test_ensure_valid_acquires_when_no_state(self):
        store = MagicMock(spec=TokenStateStore)
        store.load.return_value = None
        auth = AuthManager(
            client_id="test",
            token_store=store,
            on_acquire=lambda: "acquired",
        )
        assert auth.ensure_valid() is True
        assert auth.state.access_token == "acquired"
