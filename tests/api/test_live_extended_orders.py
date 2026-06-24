"""Contract tests for extended /api/v1/live/* order routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.config import APIConfig
from api.deps import reset_container
from api.main import create_app
from tests.api.conftest import StubLiveGateway


def test_super_order_returns_501_on_non_dhan_broker() -> None:
    reset_container()
    from types import SimpleNamespace

    app = create_app(
        config=APIConfig(auth_mode="none"),
        broker_service=SimpleNamespace(active_broker=StubLiveGateway(), active_broker_name="upstox"),
    )
    client = TestClient(app)
    resp = client.post("/api/v1/live/orders/super", json={"symbol": "RELIANCE"})
    assert resp.status_code == 501
    reset_container()


def test_edis_returns_501_on_non_dhan_broker(live_client: TestClient) -> None:
    resp = live_client.post("/api/v1/live/edis/authorize", json={"isin": "INE002A01018", "quantity": 1})
    assert resp.status_code == 501
    assert resp.headers.get("X-Data-Source") == "live_broker"


def test_gtt_returns_501_on_dhan_broker(live_client: TestClient) -> None:
    resp = live_client.post("/api/v1/live/orders/gtt", json={"symbol": "RELIANCE"})
    assert resp.status_code == 501
