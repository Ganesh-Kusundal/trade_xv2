"""P0: API bootstrap wiring — real BrokerService + shared event bus.

Verifies build_for_api() and initialize_api_services() wire a single
AsyncEventBus through BrokerService and TradingContext without mocking
the composition root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interface.api.bootstrap import initialize_api_services
from interface.ui.services.compose import build_for_api  # registers BrokerService factory


@pytest.fixture(autouse=True)
def _clear_risk_fail_open(monkeypatch):
    """Prevent leaked RISK_FAIL_OPEN from other tests breaking BrokerService."""
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_build_for_api_wires_shared_event_bus():
    """BrokerService(event_bus=) must not raise; runtime shares one bus."""
    runtime = build_for_api(skip_parity_gate=True)
    try:
        bs = runtime.broker_service
        assert bs is not None
        assert runtime.event_bus is not None
        assert runtime.event_bus is bs._event_bus

        tc = runtime.trading_context
        if tc is not None:
            assert tc.event_bus is bs._event_bus
    finally:
        if runtime.broker_service is not None:
            runtime.broker_service.close()


def test_initialize_api_services_returns_coherent_runtime(project_root: Path):
    """Full API bootstrap must return aligned event_bus + trading_context."""
    services = initialize_api_services(
        project_root,
        wire_orchestrator=False,
        skip_parity_gate=True,
    )
    try:
        runtime = services["runtime"]
        bs = services["broker_service"]
        event_bus = services["event_bus"]
        tc = services["trading_context"]

        assert runtime is not None
        assert bs is not None
        assert event_bus is not None
        assert event_bus is bs._event_bus
        assert runtime.event_bus is event_bus

        if tc is not None:
            assert tc.event_bus is event_bus
            assert services["trading_context"] is tc

        assert "datalake_gateway" in services
        assert "data_catalog" in services
        assert "view_manager" in services
    finally:
        bs = services.get("broker_service")
        if bs is not None:
            bs.close()