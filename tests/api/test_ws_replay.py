"""API WebSocket replay endpoint tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from datalake.api.config import APIConfig
from datalake.api.deps import reset_container
from datalake.api.main import create_app


@pytest.fixture
def replay_ws_app():
    reset_container()
    config = APIConfig(host="127.0.0.1", port=8000, cors_origins=[])
    app = create_app(config=config)
    yield app
    reset_container()


@pytest.fixture
def replay_ws_client(replay_ws_app):
    return TestClient(replay_ws_app)


class TestReplayWebSocket:
    def test_replay_ws_pause_stop_protocol(self, replay_ws_client: TestClient):
        create_resp = replay_ws_client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
        )
        if create_resp.status_code != 200:
            pytest.skip("Replay session creation unavailable")

        session_id = create_resp.json()["session_id"]
        with replay_ws_client.websocket_connect(f"/ws/replay/{session_id}") as ws:
            ws.send_text(json.dumps({"action": "pause"}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "replay_state"
            assert msg["state"] == "PAUSED"

            ws.send_text(json.dumps({"action": "stop"}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "replay_state"
            assert msg["state"] == "STOPPED"

    def test_replay_ws_unknown_session(self, replay_ws_client: TestClient):
        with replay_ws_client.websocket_connect("/ws/replay/missing-session-id") as ws:
            ws.send_text(json.dumps({"action": "play"}))
            messages = [json.loads(ws.receive_text()) for _ in range(2)]
            assert any(m.get("type") == "error" for m in messages)
            error = next(m for m in messages if m.get("type") == "error")
            assert error["code"] == "SESSION_NOT_FOUND"
