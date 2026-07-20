"""Architecture ratchet — deploy-profile auth unbypassable in prod/staging."""

from __future__ import annotations

import pytest

from runtime.production_config import is_production_environment, validate_production_config


def _set_env(monkeypatch, env: str, *, auth_mode: str = "none", api_key: str | None = None) -> None:
    monkeypatch.setenv("TRADEX_ENV", env)
    monkeypatch.setenv("AUTH_MODE", auth_mode)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("TRADEX_FORCE_PROD_VALIDATION", raising=False)
    if api_key is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", api_key)


def test_prod_rejects_auth_none(monkeypatch) -> None:
    _set_env(monkeypatch, "production", auth_mode="none")
    assert is_production_environment()
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        validate_production_config(surface="api")


def test_dev_allows_auth_none(monkeypatch) -> None:
    _set_env(monkeypatch, "development", auth_mode="none")
    validate_production_config(surface="api")


def test_prod_passes_with_api_key(monkeypatch) -> None:
    _set_env(monkeypatch, "production", auth_mode="api_key", api_key="explicit-secret")
    validate_production_config(surface="api")


def test_prod_rejects_api_key_without_key(monkeypatch) -> None:
    _set_env(monkeypatch, "staging", auth_mode="api_key", api_key=None)
    with pytest.raises(RuntimeError, match="API_KEY"):
        validate_production_config(surface="api")
