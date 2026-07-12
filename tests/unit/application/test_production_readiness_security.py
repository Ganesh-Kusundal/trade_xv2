"""Production readiness security checks."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.services.production_readiness import ProductionReadinessChecker


def test_secret_encryption_optional_in_production(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "production")
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    checker = ProductionReadinessChecker(MagicMock())
    passed, message = checker._check_secret_encryption()
    assert passed is True
    assert "plaintext" in message.lower()


def test_api_key_required_in_production(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "staging")
    monkeypatch.delenv("API_KEY", raising=False)
    checker = ProductionReadinessChecker(MagicMock())
    passed, message = checker._check_api_key_explicit()
    assert passed is False
    assert "API_KEY" in message