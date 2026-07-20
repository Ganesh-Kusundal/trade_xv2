"""Production fail-open env flags must be rejected in prod/staging (Phase 1b)."""

from __future__ import annotations

import pytest

from runtime.production_config import is_production_environment, validate_production_config

# ponytail: explicit list — add new fail-open flags here when introduced.
_FORBIDDEN_PROD_FLAGS: tuple[tuple[str, str], ...] = (
    ("RISK_FAIL_OPEN", "1"),
    ("SKIP_PARITY_GATE", "1"),
)


def _set_prod(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("TRADEX_FORCE_PROD_VALIDATION", raising=False)


@pytest.mark.parametrize("flag,value", _FORBIDDEN_PROD_FLAGS)
def test_production_rejects_fail_open_flags(monkeypatch, flag: str, value: str) -> None:
    _set_prod(monkeypatch)
    monkeypatch.setenv(flag, value)
    assert is_production_environment()
    with pytest.raises(RuntimeError):
        validate_production_config(surface="runtime")


def test_dev_allows_unset_fail_open_flags(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_ENV", "development")
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    monkeypatch.delenv("SKIP_PARITY_GATE", raising=False)
    validate_production_config(surface="runtime")
