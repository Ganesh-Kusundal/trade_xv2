"""Runtime factory bootstrap tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from interface.ui.services.compose import build_for_api
from runtime.factory import BuildOptions, build_from_broker_service


@pytest.fixture(autouse=True)
def _clear_risk_fail_open(monkeypatch):
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    yield
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)


def test_build_for_api_wires_real_broker_service_with_composition_bus():
    """API bootstrap uses create_api_event_bus and real BrokerService."""
    runtime = build_for_api(skip_parity_gate=True)
    try:
        assert runtime.broker_service is not None
        assert runtime.event_bus is not None
        assert runtime.event_bus is runtime.broker_service._event_bus
    finally:
        runtime.broker_service.close()


def test_create_api_event_bus_returns_async_wrapper():
    from infrastructure.event_bus.async_event_bus import AsyncEventBus
    from runtime.composition import create_api_event_bus

    bus, config = create_api_event_bus(maxsize=100)
    assert isinstance(bus, AsyncEventBus)
    assert config["bus_type"] == "async"
    bus.stop()


def test_build_for_api_uses_composition_module():
    """create_api_event_bus must be invoked during API bootstrap."""
    from runtime.composition import create_api_event_bus as real_create

    with patch(
        "runtime.composition.create_api_event_bus",
        wraps=real_create,
    ) as create_bus:
        runtime = build_for_api(skip_parity_gate=True)
        try:
            create_bus.assert_called_once()
            assert runtime.event_bus is runtime.broker_service._event_bus
        finally:
            runtime.broker_service.close()


def test_authorize_risk_fail_open_requires_explicit_env(monkeypatch):
    """authorize_risk_fail_open must not set RISK_FAIL_OPEN without opt-in env."""
    monkeypatch.delenv("TRADEX_AUTHORIZE_RISK_FAIL_OPEN", raising=False)
    opts = BuildOptions(authorize_risk_fail_open=True)
    with pytest.raises(RuntimeError, match="TRADEX_AUTHORIZE_RISK_FAIL_OPEN"):
        build_from_broker_service(MagicMock(), options=opts)


def test_authorize_risk_fail_open_sets_env_when_explicitly_opted_in(monkeypatch):
    monkeypatch.setenv("TRADEX_AUTHORIZE_RISK_FAIL_OPEN", "1")
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    opts = BuildOptions(
        authorize_risk_fail_open=True,
        skip_parity_gate=True,
    )
    bs = MagicMock()
    bs.active_broker = MagicMock()
    bs.trading_context = None
    bs._gateway = None
    bs._upstox_gateway = None
    bs._active_name = "dhan"
    bs.lifecycle = MagicMock()
    bs.http_observability = None
    bs._readiness_report = None
    bs.live_actionable = False
    bs.active_broker_name = "dhan"
    bs._event_bus = None
    with patch("runtime.production_config.validate_production_config"):
        build_from_broker_service(bs, options=opts)
    assert __import__("os").environ.get("RISK_FAIL_OPEN") == "1"
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)