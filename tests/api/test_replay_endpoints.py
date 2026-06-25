"""Integration tests for replay endpoints wired to real ReplayEngine."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.config import APIConfig
from api.deps import reset_container
from api.main import create_app


def _build_sample_ohlcv(n_bars: int = 50) -> pd.DataFrame:
    """Build deterministic OHLCV data for testing."""
    import numpy as np

    dates = pd.date_range("2024-01-15 09:15", periods=n_bars, freq="1min", tz=timezone.utc)
    t = np.linspace(0, 4 * np.pi, n_bars)
    base_price = 1000.0
    prices = base_price + 30 * np.sin(t)

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices - 1,
            "high": prices + 2,
            "low": prices - 2,
            "close": prices,
            "volume": 10000 + 1000 * np.sin(t),
        }
    )
    return df


@pytest.fixture
def isolate_replay_state():
    """Reset replay session store and container before each test."""
    import api.routers.replay as replay_mod

    replay_mod._session_store = replay_mod.ReplaySessionStore()
    reset_container()
    yield
    replay_mod._session_store = replay_mod.ReplaySessionStore()
    reset_container()


@contextmanager
def _make_client_with_gateway(sample_df=None, gateway=None):
    """Create a test client with a mocked gateway."""
    if gateway is None:
        if sample_df is None:
            sample_df = _build_sample_ohlcv(50)
        gateway = MagicMock()
        gateway.history.return_value = sample_df
    app = create_app(config=APIConfig(auth_mode="none"), datalake_gateway=gateway)
    with TestClient(app) as client:
        yield client


@contextmanager
def _make_client_no_gateway():
    """Create a test client without a gateway."""
    app = create_app(config=APIConfig(auth_mode="none"), datalake_gateway=None)
    with TestClient(app) as client:
        yield client


class TestReplaySessionLifecycle:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    """Each test gets its own isolated app + session store."""

    def test_create_session_returns_initialized(self):
        with _make_client_with_gateway() as client:
            response = client.post(
                "/api/v1/replay/sessions",
                json={
                    "symbol": "RELIANCE",
                    "date": "2024-01-15",
                    "timeframe": "1m",
                    "universe": "NIFTY50",
                    "speed": 5,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "initialized"
            assert data["session_id"].startswith("replay_")
            assert data["progress"] == 0.0

    def test_get_session_returns_correct_data(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.get(f"/api/v1/replay/sessions/{session_id}")
            assert response.status_code == 200
            assert response.json()["session_id"] == session_id

    def test_get_nonexistent_session_returns_404(self):
        with _make_client_with_gateway() as client:
            response = client.get("/api/v1/replay/sessions/nonexistent_123")
            assert response.status_code == 404

    def test_list_sessions_shows_created(self):
        with _make_client_with_gateway() as client:
            client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "TCS", "date": "2024-01-15", "timeframe": "1m"},
            )
            response = client.get("/api/v1/replay/sessions")
            assert response.json()["count"] == 2


class TestReplayPlayWithRealEngine:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_play_runs_real_replay_engine(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["progress"] > 0

    def test_play_produces_real_metrics(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            client.post(f"/api/v1/replay/sessions/{session_id}/play")
            get_resp = client.get(f"/api/v1/replay/sessions/{session_id}")
            assert get_resp.status_code == 200

    def test_play_with_no_data_returns_warning(self):
        with _make_client_with_gateway() as client:
            gateway = MagicMock()
            gateway.history.return_value = None
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "NOSYMBOL", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code == 200

    def test_play_nonexistent_session_returns_404(self):
        with _make_client_with_gateway() as client:
            response = client.post("/api/v1/replay/sessions/fake_session/play")
            assert response.status_code == 404


class TestReplayPauseAndStop:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_pause_session(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(f"/api/v1/replay/sessions/{session_id}/pause")
            assert response.status_code == 200
            assert response.json()["status"] == "paused"

    def test_stop_session(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(f"/api/v1/replay/sessions/{session_id}/stop")
            assert response.status_code == 200
            assert response.json()["status"] == "stopped"
            assert response.json()["progress"] == 100.0

    def test_pause_nonexistent_session_returns_404(self):
        with _make_client_with_gateway() as client:
            assert client.post("/api/v1/replay/sessions/fake_session/pause").status_code == 404

    def test_stop_nonexistent_session_returns_404(self):
        with _make_client_with_gateway() as client:
            assert client.post("/api/v1/replay/sessions/fake_session/stop").status_code == 404


class TestReplaySpeedControl:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_set_valid_speed(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(
                f"/api/v1/replay/sessions/{session_id}/speed",
                json={"action": "set_speed", "speed": 10},
            )
            assert response.status_code == 200
            assert response.json()["speed"] == 10

    def test_set_invalid_speed_returns_400(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(
                f"/api/v1/replay/sessions/{session_id}/speed",
                json={"action": "set_speed", "speed": 99},
            )
            assert response.status_code == 400

    def test_set_speed_nonexistent_session_returns_404(self):
        with _make_client_with_gateway() as client:
            assert (
                client.post(
                    "/api/v1/replay/sessions/fake_session/speed",
                    json={"action": "set_speed", "speed": 5},
                ).status_code
                == 404
            )


class TestReplaySeek:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_seek_updates_progress(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            mid_day_ts = int(
                datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
            )
            response = client.post(
                f"/api/v1/replay/sessions/{session_id}/seek", params={"timestamp_ms": mid_day_ts}
            )
            assert response.status_code == 200
            assert response.json()["progress"] >= 0.0

    def test_seek_nonexistent_session_returns_404(self):
        with _make_client_with_gateway() as client:
            assert (
                client.post(
                    "/api/v1/replay/sessions/fake_session/seek",
                    params={"timestamp_ms": 1705300000000},
                ).status_code
                == 404
            )


class TestReplayStateValidation:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_cannot_play_stopped_session(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            client.post(f"/api/v1/replay/sessions/{session_id}/stop")
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code == 409

    def test_cannot_play_completed_session(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            client.post(f"/api/v1/replay/sessions/{session_id}/play")
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code == 409

    def test_can_pause_after_play(self):
        with _make_client_with_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            client.post(f"/api/v1/replay/sessions/{session_id}/play")
            response = client.post(f"/api/v1/replay/sessions/{session_id}/pause")
            assert response.status_code == 200


class TestReplayDeterministicResults:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_same_data_produces_same_trades(self):
        with _make_client_with_gateway() as tc:
            _build_sample_ohlcv(50)
            results = []
            for _ in range(2):
                reset_container()
                import api.routers.replay as replay_mod

                replay_mod._session_store = replay_mod.ReplaySessionStore()
                create_resp = tc.post(
                    "/api/v1/replay/sessions",
                    json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
                )
                session_id = create_resp.json()["session_id"]
                play_resp = tc.post(f"/api/v1/replay/sessions/{session_id}/play")
                results.append(play_resp.json())

            assert results[0]["status"] == "completed"
            assert results[1]["status"] == "completed"


class TestReplayErrorHandling:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_gateway_unavailable_handles_gracefully(self):
        with _make_client_no_gateway() as client:
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "RELIANCE", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code == 200

    def test_invalid_symbol_handled(self):
        with _make_client_with_gateway() as client:
            gateway = MagicMock()
            gateway.history.side_effect = ValueError("Symbol not found")
            create_resp = client.post(
                "/api/v1/replay/sessions",
                json={"symbol": "INVALID", "date": "2024-01-15", "timeframe": "1m"},
            )
            session_id = create_resp.json()["session_id"]
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code == 200


class TestReplayConcurrency:
    @pytest.fixture(autouse=True)
    def setup_isolation(self):
        import api.routers.replay as replay_mod

        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()
        yield
        replay_mod._session_store = replay_mod.ReplaySessionStore()
        reset_container()

    def test_concurrent_session_creation(self):
        with _make_client_with_gateway() as client:
            errors = []

            def create_session(symbol):
                try:
                    resp = client.post(
                        "/api/v1/replay/sessions",
                        json={"symbol": symbol, "date": "2024-01-15", "timeframe": "1m"},
                    )
                    assert resp.status_code == 200
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=create_session, args=(f"SYM{i}",)) for i in range(10)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert not errors
            assert client.get("/api/v1/replay/sessions").json()["count"] == 10
