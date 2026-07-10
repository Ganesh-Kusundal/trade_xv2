"""Parity between doctor diagnostics and live /readyz surface."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from interface.api.config import APIConfig
from interface.api.deps import reset_container
from interface.api.main import create_app
from application.services.production_readiness import ProductionReadinessChecker
from interface.ui.diagnostics.doctor import DoctorDiagnostics
from tests.api.conftest import StubLiveGateway


def test_readyz_check_names_are_structured_like_doctor() -> None:
    """readyz returns named checks; doctor quick-check uses the same shape."""
    reset_container()
    gateway = StubLiveGateway()
    broker_service = SimpleNamespace(
        active_broker=gateway,
        active_broker_name="dhan",
        lifecycle=MagicMock(
            service_names=MagicMock(return_value=[]), health_snapshot=MagicMock(return_value={})
        ),
        _trading_context=None,
        _gateway=MagicMock(_conn=MagicMock(market_feed=MagicMock(), order_stream=MagicMock())),
        _http_observability=MagicMock(),
        _oms_risk_manager=None,
        _http_sessions=[],
    )
    app = create_app(config=APIConfig(auth_mode="none"), broker_service=broker_service)
    client = TestClient(app)

    doctor_names = {
        name
        for name, _status, _detail in DoctorDiagnostics(broker_service, gateway).run_all_checks()
    }
    assert doctor_names  # doctor always returns at least one check

    ready_report = ProductionReadinessChecker(broker_service).run()
    ready_names = {c.name for c in ready_report.checks}
    assert ready_names  # readiness checker returns infrastructure checks

    # Live readyz exposes the readiness checker names (subset contract for operators).
    resp = client.get("/api/v1/live/readyz")
    assert resp.status_code in (200, 503)
    payload = resp.json() if resp.status_code == 200 else resp.json().get("detail", resp.json())
    checks = payload.get("checks", [])
    readyz_names = {c["name"] for c in checks if isinstance(c, dict) and "name" in c}
    assert readyz_names == ready_names
    reset_container()
