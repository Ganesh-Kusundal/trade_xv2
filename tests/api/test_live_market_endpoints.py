"""Contract tests for /api/v1/live/* broker-backed endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interface.api.config import APIConfig
from interface.api.deps import reset_container
from interface.api.main import create_app


class TestLiveMarketEndpoints:
    def test_live_quote_headers(self, live_client: TestClient) -> None:
        resp = live_client.get("/api/v1/live/quote/RELIANCE")
        assert resp.status_code == 200
        assert resp.headers.get("X-Data-Source") == "live_broker"
        assert resp.headers.get("X-Broker-Name") == "dhan"
        assert resp.json()["symbol"] == "RELIANCE"

    def test_live_positions(self, live_client: TestClient) -> None:
        resp = live_client.get("/api/v1/live/positions")
        assert resp.status_code == 200
        assert resp.headers.get("X-Data-Source") == "live_broker"

    def test_live_futures_chain(self, live_client: TestClient) -> None:
        resp = live_client.get("/api/v1/live/futures/chain/NIFTY")
        assert resp.status_code == 200
        assert resp.json()["underlying"] == "NIFTY"

    def test_live_broker_unavailable_returns_503(self) -> None:
        reset_container()
        app = create_app(config=APIConfig(auth_mode="none"), broker_service=None)
        client = TestClient(app)
        resp = client.get("/api/v1/live/quote/RELIANCE")
        assert resp.status_code == 503
        reset_container()
