"""Tests for production boot validation."""

from __future__ import annotations

import pytest

from runtime.production_config import is_production_environment, validate_production_config


@pytest.fixture
def prod_env(monkeypatch):
    monkeypatch.setenv("TRADEX_ENV", "production")
    monkeypatch.setenv("TRADEX_FORCE_PROD_VALIDATION", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


def test_skipped_in_development(monkeypatch):
    monkeypatch.setenv("TRADEX_ENV", "development")
    validate_production_config(surface="api")


def test_api_requires_auth_in_production(prod_env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "none")
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        validate_production_config(surface="api")


def test_api_passes_with_api_key(prod_env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "api_key")
    monkeypatch.setenv("API_KEY", "test-secret-key")
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    monkeypatch.delenv("SKIP_PARITY_GATE", raising=False)
    validate_production_config(surface="api")


def test_runtime_rejects_risk_fail_open(prod_env, monkeypatch):
    monkeypatch.setenv("RISK_FAIL_OPEN", "1")
    with pytest.raises(RuntimeError, match="RISK_FAIL_OPEN"):
        validate_production_config(surface="runtime")


def test_runtime_rejects_skip_parity_gate(prod_env, monkeypatch):
    monkeypatch.setenv("SKIP_PARITY_GATE", "1")
    with pytest.raises(RuntimeError, match="SKIP_PARITY_GATE"):
        validate_production_config(surface="runtime")


def test_runtime_rejects_live_target_in_production(prod_env, monkeypatch):
    monkeypatch.setenv("TRADEX_EXECUTION_TARGET", "live")
    with pytest.raises(RuntimeError, match="ADR-0013"):
        validate_production_config(surface="runtime")


def test_is_production_environment_false_in_dev(monkeypatch):
    monkeypatch.setenv("TRADEX_ENV", "development")
    assert is_production_environment() is False
