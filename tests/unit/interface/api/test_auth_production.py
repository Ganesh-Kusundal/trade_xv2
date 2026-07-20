"""Production/staging API key startup guards (SEC-009)."""

from __future__ import annotations

import pytest

import interface.api.auth as auth


@pytest.fixture(autouse=True)
def _restore_auth_state():
    saved_mode = auth.AUTH_MODE
    saved_key = auth.API_KEY
    yield
    auth.AUTH_MODE = saved_mode
    auth.API_KEY = saved_key
    auth._AuthConfig.AUTH_MODE = saved_mode
    auth._AuthConfig.API_KEY = saved_key


@pytest.mark.parametrize("tradex_env", ["production", "staging"])
def test_configure_fails_without_api_key_in_production(monkeypatch, tradex_env: str) -> None:
    monkeypatch.setenv("TRADEX_ENV", tradex_env)
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API_KEY must be set explicitly"):
        auth.configure(auth_mode="api_key")


def test_configure_accepts_explicit_api_key_in_production(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "production")
    auth.configure(auth_mode="api_key", api_key="prod-secret-key")
    assert auth.API_KEY == "prod-secret-key"


def test_configure_generates_ephemeral_key_in_development(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "development")
    monkeypatch.delenv("API_KEY", raising=False)
    auth.configure(auth_mode="api_key")
    assert len(auth.API_KEY) > 0
