"""Datalake unit tests — ensure active exchange adapter is wired."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _wire_exchange_for_datalake_tests(monkeypatch):
    """Register NSE via entry-point discovery (or legacy fallback)."""
    from datalake import exchange_registry
    from datalake.exchange_registry import wire_exchange_plugins

    exchange_registry._ExchangeState._active_adapter = None
    exchange_registry._ExchangeState._discovered = False
    monkeypatch.delenv("TRADEX_LEGACY_NSE_DEFAULT", raising=False)
    wire_exchange_plugins()
    yield
