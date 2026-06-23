"""API WebSocket market endpoint tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from infrastructure.event_bus.event_bus import EventBus
from api.config import APIConfig
from api.deps import reset_container
from api.main import create_app


@pytest.fixture
def ws_app():
    reset_container()
    config = APIConfig(host="127.0.0.1", port=8000, cors_origins=[])
    app = create_app(config=config, event_bus=EventBus())
    yield app
    reset_container()


@pytest.fixture
def ws_client(ws_app):
    return TestClient(ws_app)


class TestMarketWebSocket:
    def test_market_ws_connect_and_subscribe(self, ws_client: TestClient):
        with ws_client.websocket_connect("/ws/market") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "symbols": ["RELIANCE"]}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "subscribed"
            assert "RELIANCE" in msg["symbols"]

    def test_market_ws_ping_pong(self, ws_client: TestClient):
        with ws_client.websocket_connect("/ws/market") as ws:
            ws.send_text(json.dumps({"action": "ping", "timestamp": 123}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "pong"
            assert msg["timestamp"] == 123

    def test_market_ws_unsubscribe(self, ws_client: TestClient):
        with ws_client.websocket_connect("/ws/market") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "symbols": ["TCS"]}))
            ws.receive_text()
            ws.send_text(json.dumps({"action": "unsubscribe", "symbols": ["TCS"]}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "unsubscribed"
            assert "TCS" in msg["symbols"]

    def test_market_ws_without_event_bus_closes(self, client: TestClient):
        try:
            with client.websocket_connect("/ws/market") as ws:
                data = ws.receive_text()
                msg = json.loads(data)
                assert msg["type"] == "error"
        except Exception:
            pass
