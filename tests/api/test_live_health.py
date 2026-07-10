"""Live broker health endpoint tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.config import APIConfig
from api.deps import reset_container
from api.main import create_app


class _HealthGateway:
    def describe(self):
        return {"connected": True}

    def capabilities(self):
        from domain.capabilities.broker_capabilities import BrokerCapabilities

        return BrokerCapabilities(broker_id="stub")


@pytest.fixture
def health_client():
    reset_container()

    class _Checker:
        def run(self):
            from application.services.production_readiness import ReadinessReport

            return ReadinessReport()

    import application.services.production_readiness as pr

    original = pr.ProductionReadinessChecker
    pr.ProductionReadinessChecker = lambda svc: _Checker()  # type: ignore[misc]
    broker_service = SimpleNamespace(
        active_broker=_HealthGateway(),
        active_broker_name="dhan",
    )
    app = create_app(config=APIConfig(auth_mode="none"), broker_service=broker_service)
    client = TestClient(app)
    yield client
    pr.ProductionReadinessChecker = original
    reset_container()


def test_live_health(health_client: TestClient) -> None:
    resp = health_client.get("/api/v1/live/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Data-Source") == "live_broker"


def test_live_capabilities(health_client: TestClient) -> None:
    resp = health_client.get("/api/v1/live/capabilities")
    assert resp.status_code == 200
    assert "capabilities" in resp.json()


def test_live_readyz(health_client: TestClient) -> None:
    resp = health_client.get("/api/v1/live/readyz")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True
