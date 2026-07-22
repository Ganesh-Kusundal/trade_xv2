"""P0: API bootstrap wiring — real BrokerService + shared event bus.

Verifies build_for_api() and initialize_api_services() wire a single
AsyncEventBus through BrokerService and TradingContext without mocking
the composition root.

ponytail: block .env.local in tests — full Dhan bootstrap (load_instruments,
websockets) hangs CI when credentials exist locally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interface.api.bootstrap import initialize_api_services
from interface.ui.services.compose import build_for_api  # registers BrokerService factory
from tests.conftest import build_test_trading_context


@pytest.fixture(autouse=True)
def _clear_risk_fail_open(monkeypatch):
    """Prevent leaked RISK_FAIL_OPEN from other tests breaking BrokerService."""
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)


@pytest.fixture(autouse=True)
def _block_live_env_bootstrap(monkeypatch, tmp_path):
    """Never run live Dhan/Upstox bootstrap during API wiring tests."""
    monkeypatch.setattr(
        "interface.ui.services.broker_service._ENV_PATH",
        tmp_path / "missing.env.local",
    )
    monkeypatch.setattr(
        "interface.ui.services.broker_registry.resolve_env_path",
        lambda _broker_id: None,
    )


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _lightweight_broker_service_factory():
    """BrokerService with TradingContext + mock dhan gateway — no network I/O."""

    def factory(*, event_bus=None):
        from interface.ui.services.broker_service import BrokerService
        from interface.ui.services.broker_registry import create_seeded_mock_broker
        from domain.enums import BrokerId

        ctx = build_test_trading_context(event_bus=event_bus)
        bs = BrokerService(event_bus=ctx.event_bus)
        bs._initialized = True
        bs._trading_context = ctx
        bs._gateway = create_seeded_mock_broker(BrokerId.DHAN)
        bs._active_name = BrokerId.DHAN
        bs._live_actionable = True
        bs._paper = None
        bs._mock = None
        return bs

    return factory


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
        broker_service_factory=_lightweight_broker_service_factory(),
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

        assert tc is not None
        assert tc.event_bus is event_bus
        assert services["trading_context"] is tc

        exec_composer = services.get("execution_composer")
        assert exec_composer is not None
        assert exec_composer._order_manager is tc.order_manager, (
            "ExecutionComposer must share TradingContext OrderManager (P0 split-brain fix)"
        )

        assert "datalake_gateway" in services
        assert "data_catalog" in services
        assert "view_manager" in services
    finally:
        bs = services.get("broker_service")
        if bs is not None and hasattr(bs, "close"):
            bs.close()


def test_lightweight_factory_skips_live_bootstrap(project_root: Path):
    """Regression: bootstrap must not touch .env.local when factory is injected."""
    services = initialize_api_services(
        project_root,
        wire_orchestrator=False,
        skip_parity_gate=True,
        broker_service_factory=_lightweight_broker_service_factory(),
    )
    try:
        bs = services["broker_service"]
        assert bs._initialized is True
        assert services["trading_context"] is bs._trading_context
    finally:
        bs = services.get("broker_service")
        if bs is not None and hasattr(bs, "close"):
            bs.close()
