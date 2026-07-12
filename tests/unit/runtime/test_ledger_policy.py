"""runtime.ledger_policy — ADR-015 feature flag."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from runtime.ledger_policy import ledger_authority_enabled, resolve_execution_ledger


def test_ledger_authority_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADEX_LEDGER_AUTHORITY", raising=False)
    assert ledger_authority_enabled() is False
    assert resolve_execution_ledger() is None


def test_ledger_authority_on_invokes_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_LEDGER_AUTHORITY", "1")
    builder = MagicMock(return_value="ledger")
    assert resolve_execution_ledger(builder=builder) == "ledger"
    builder.assert_called_once()