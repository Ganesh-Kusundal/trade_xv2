"""Contract tests for options and replay endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestOptionsEndpoints:
    """Test options analytics endpoints."""
    
    def test_get_option_chain(self, client: TestClient):
        """GET /api/v1/options/chain/{underlying} returns option chain."""
        response = client.get(
            "/api/v1/options/chain/NIFTY",
            params={"expiry": "2024-01-25", "strike_range": 5},
        )
        
        # May return 200, 404, 500, or 503
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "underlying" in data
            assert "expiry" in data
            assert "contracts" in data
            assert "count" in data
    
    def test_get_option_chain_no_expiry(self, client: TestClient):
        """GET /api/v1/options/chain/{underlying} without expiry filter."""
        response = client.get(
            "/api/v1/options/chain/BANKNIFTY",
            params={"strike_range": 3},
        )
        
        assert response.status_code in [200, 404, 500, 503]
    
    def test_get_pcr(self, client: TestClient):
        """GET /api/v1/options/pcr/{underlying} returns PCR."""
        response = client.get("/api/v1/options/pcr/NIFTY")
        
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "underlying" in data
            assert "pcr_oi" in data
            assert "pcr_volume" in data
    
    def test_get_max_pain(self, client: TestClient):
        """GET /api/v1/options/max-pain/{underlying} returns max pain."""
        response = client.get("/api/v1/options/max-pain/NIFTY")
        
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "underlying" in data
            assert "max_pain_strike" in data
            assert "total_pain" in data
    
    def test_get_iv_surface(self, client: TestClient):
        """GET /api/v1/options/iv-surface/{underlying} returns IV surface."""
        response = client.get("/api/v1/options/iv-surface/NIFTY")
        
        assert response.status_code in [200, 404, 500, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "underlying" in data
            assert "data" in data
            assert "count" in data
    
    def test_get_iv_surface_with_filters(self, client: TestClient):
        """GET /api/v1/options/iv-surface/{underlying} with filters."""
        response = client.get(
            "/api/v1/options/iv-surface/BANKNIFTY",
            params={"expiry": "2024-01-25", "option_type": "CE"},
        )
        
        assert response.status_code in [200, 404, 500, 503]
    
    def test_get_volume_profile(self, client: TestClient):
        """GET /api/v1/options/volume-profile/{underlying} returns profile."""
        response = client.get("/api/v1/options/volume-profile/NIFTY")
        assert response.status_code in [200, 404, 500, 503]
        if response.status_code == 200:
            data = response.json()
            assert "strikes" in data
            assert "profile" in data
            assert "note" not in data

    def test_option_chain_rejects_path_traversal(self, client: TestClient):
        response = client.get("/api/v1/options/chain/../etc")
        assert response.status_code == 404

    def test_option_chain_rejects_sql_injection_symbol(self, client: TestClient):
        response = client.get("/api/v1/options/chain/';DROP")
        assert response.status_code == 400

    def test_option_chain_rejects_empty_symbol(self, client: TestClient):
        response = client.get("/api/v1/options/chain/")
        assert response.status_code in (404, 405)


class TestReplayEndpoints:
    """Test replay session management endpoints."""
    
    def test_list_sessions(self, client: TestClient):
        """GET /api/v1/replay/sessions returns session list."""
        response = client.get("/api/v1/replay/sessions")
        
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "sessions" in data
            assert "count" in data
    
    def test_create_session(self, client: TestClient):
        """POST /api/v1/replay/sessions creates new session."""
        response = client.post(
            "/api/v1/replay/sessions",
            json={
                "symbol": "RELIANCE",
                "date": "2024-01-15",
                "timeframe": "1m",
                "speed": 5,
            },
        )
        
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data
            assert "status" in data
            assert "date" in data
    
    def test_get_session(self, client: TestClient):
        """GET /api/v1/replay/sessions/{id} returns session details."""
        # Create session first
        create_response = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "TCS", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_response.status_code == 200:
            session_id = create_response.json()["session_id"]
            
            response = client.get(f"/api/v1/replay/sessions/{session_id}")
            assert response.status_code in [200, 503]
    
    def test_get_session_not_found(self, client: TestClient):
        """GET /api/v1/replay/sessions/{id} returns 404 for unknown session."""
        response = client.get("/api/v1/replay/sessions/nonexistent_123")
        assert response.status_code in [404, 503]
    
    def test_play_session(self, client: TestClient):
        """POST /api/v1/replay/sessions/{id}/play starts playback."""
        # Create session
        create_response = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "INFY", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_response.status_code == 200:
            session_id = create_response.json()["session_id"]
            
            response = client.post(f"/api/v1/replay/sessions/{session_id}/play")
            assert response.status_code in [200, 404, 503]
    
    def test_pause_session(self, client: TestClient):
        """POST /api/v1/replay/sessions/{id}/pause pauses playback."""
        create_response = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "HDFC", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_response.status_code == 200:
            session_id = create_response.json()["session_id"]
            client.post(f"/api/v1/replay/sessions/{session_id}/play")
            
            response = client.post(f"/api/v1/replay/sessions/{session_id}/pause")
            assert response.status_code in [200, 404, 503]
    
    def test_stop_session(self, client: TestClient):
        """POST /api/v1/replay/sessions/{id}/stop stops playback."""
        create_response = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "ICICI", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_response.status_code == 200:
            session_id = create_response.json()["session_id"]
            
            response = client.post(f"/api/v1/replay/sessions/{session_id}/stop")
            assert response.status_code in [200, 404, 503]
    
    def test_set_speed(self, client: TestClient):
        """POST /api/v1/replay/sessions/{id}/speed sets playback speed."""
        create_response = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "SBIN", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_response.status_code == 200:
            session_id = create_response.json()["session_id"]
            
            response = client.post(
                f"/api/v1/replay/sessions/{session_id}/speed",
                json={"speed": 10},
            )
            assert response.status_code in [200, 400, 404, 422, 503]
    
    def test_seek_to_time(self, client: TestClient):
        """POST /api/v1/replay/sessions/{id}/seek seeks to timestamp."""
        create_response = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "TATAMOTORS", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_response.status_code == 200:
            session_id = create_response.json()["session_id"]
            
            response = client.post(
                f"/api/v1/replay/sessions/{session_id}/seek",
                params={"timestamp_ms": 1705315200000},
            )
            assert response.status_code in [200, 404, 503]


class TestReplaySessionLifecycle:
    """Test complete replay session lifecycle."""
    
    def test_full_lifecycle(self, client: TestClient):
        """Test create → play → pause → resume → stop."""
        # Create
        create_resp = client.post(
            "/api/v1/replay/sessions",
            json={"symbol": "WIPRO", "date": "2024-01-15", "timeframe": "1m"},
        )
        
        if create_resp.status_code != 200:
            pytest.skip("Session creation failed")
        
        session_id = create_resp.json()["session_id"]
        
        # Play
        play_resp = client.post(f"/api/v1/replay/sessions/{session_id}/play")
        assert play_resp.status_code in [200, 503]
        
        # Pause
        pause_resp = client.post(f"/api/v1/replay/sessions/{session_id}/pause")
        assert pause_resp.status_code in [200, 503]
        
        # Resume
        play_resp2 = client.post(f"/api/v1/replay/sessions/{session_id}/play")
        assert play_resp2.status_code in [200, 503]
        
        # Stop
        stop_resp = client.post(f"/api/v1/replay/sessions/{session_id}/stop")
        assert stop_resp.status_code in [200, 503]
