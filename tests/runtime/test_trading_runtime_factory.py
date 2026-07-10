"""Runtime factory bootstrap tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runtime.trading_runtime_factory import TradingRuntimeFactory


def test_build_for_api_uses_composition_module():
    """API bootstrap must use runtime.composition.create_api_event_bus."""
    mock_bus = MagicMock()
    mock_bs = MagicMock()
    with patch(
        "runtime.composition.create_api_event_bus",
        return_value=(mock_bus, None),
    ) as create_bus:
        with patch(
            "interface.ui.services.broker_service.BrokerService",
            return_value=mock_bs,
        ):
            with patch.object(
                TradingRuntimeFactory,
                "build_from_broker_service",
                return_value=MagicMock(),
            ) as build_from_bs:
                TradingRuntimeFactory.build_for_api()
    create_bus.assert_called_once()
    build_from_bs.assert_called_once_with(mock_bs)


def test_authorize_risk_fail_open_requires_explicit_env(monkeypatch):
    """authorize_risk_fail_open must not set RISK_FAIL_OPEN without opt-in env."""
    monkeypatch.delenv("TRADEX_AUTHORIZE_RISK_FAIL_OPEN", raising=False)
    factory = TradingRuntimeFactory(authorize_risk_fail_open=True)
    with pytest.raises(RuntimeError, match="TRADEX_AUTHORIZE_RISK_FAIL_OPEN"):
        factory.build_from_broker_service(MagicMock())


def test_authorize_risk_fail_open_sets_env_when_explicitly_opted_in(monkeypatch):
    monkeypatch.setenv("TRADEX_AUTHORIZE_RISK_FAIL_OPEN", "1")
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    factory = TradingRuntimeFactory(
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
        factory.build_from_broker_service(bs)
    assert __import__("os").environ.get("RISK_FAIL_OPEN") == "1"
