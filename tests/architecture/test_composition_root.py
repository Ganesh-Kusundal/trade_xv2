"""ADR-017 — single composition root facade exists and is importable."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_runtime_factory_build_is_public_entry() -> None:
    from runtime import build, build_from_broker_service
    from runtime.factory import BuildOptions

    assert callable(build)
    assert callable(build_from_broker_service)
    assert BuildOptions is not None


@pytest.mark.architecture
def test_trading_runtime_factory_is_deprecated_reexport() -> None:
    """TradingRuntimeFactory is now a deprecated wrapper; factory.build is the real root."""
    import runtime.trading_runtime_factory as trf_mod

    src = inspect.getsource(trf_mod.TradingRuntimeFactory)
    assert "deprecated" in src.lower() or "DeprecationWarning" in src


@pytest.mark.architecture
def test_ledger_policy_defaults_off() -> None:
    import runtime.ledger_policy as policy

    assert policy._ENV_LEDGER_AUTHORITY == "TRADEX_LEDGER_AUTHORITY"
    src = inspect.getsource(policy.ledger_authority_enabled)
    assert '"0"' in src or "'0'" in src