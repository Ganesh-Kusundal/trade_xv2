"""Tests for API authentication."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import APIConfig
from api.main import create_app


class TestAuthDisabled:
    """Test that auth is disabled by default (AUTH_MODE=none)."""

    def test_public_endpoints_accessible_without_auth(self):
        """Health endpoints should always be accessible."""
        app = create_app(config=APIConfig(auth_mode="none"))
        client = TestClient(app)

        response = client.get("/api/v1/health")
        assert response.status_code == 200

        response = client.get("/api/v1/health/readyz")
        assert response.status_code in (200, 503)  # 503 if services not ready

    def test_protected_endpoints_accessible_when_auth_disabled(self):
        """When AUTH_MODE=none, all endpoints should be accessible (not 401)."""
        app = create_app(config=APIConfig(auth_mode="none"))
        client = TestClient(app)

        # These should NOT return 401 (auth error)
        # They may return 200, 500, or 503 depending on service state
        response = client.get("/api/v1/symbols/search?q=RELIANCE")
        assert response.status_code != 401  # Not an auth error


class TestAuthEnabled:
    """Test that API key authentication works when enabled."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, monkeypatch):
        """Enable auth mode and set API key for tests."""
        monkeypatch.setenv("AUTH_MODE", "api_key")
        monkeypatch.setenv("API_KEY", "test-secret-key-123")
        # Force reimport of auth module to pick up new env vars
        import importlib

        import api.auth

        importlib.reload(api.auth)

    def test_public_endpoints_still_accessible(self):
        """Health/docs should be accessible even when auth is enabled."""
        app = create_app(config=APIConfig(auth_mode="api_key", api_key="test-secret-key-123"))
        client = TestClient(app)

        response = client.get("/api/v1/health")
        assert response.status_code == 200

        response = client.get("/docs")
        assert response.status_code == 200

    def test_protected_endpoints_reject_missing_key(self):
        """Protected endpoints should return 401 without API key."""
        app = create_app(config=APIConfig(auth_mode="api_key", api_key="test-secret-key-123"))
        client = TestClient(app)

        response = client.get("/api/v1/symbols/search?q=RELIANCE")
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_protected_endpoints_reject_invalid_key(self):
        """Protected endpoints should return 401 with wrong API key."""
        app = create_app(config=APIConfig(auth_mode="api_key", api_key="test-secret-key-123"))
        client = TestClient(app)

        response = client.get(
            "/api/v1/symbols/search?q=RELIANCE",
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_protected_endpoints_accept_valid_key(self):
        """Protected endpoints should accept valid API key (not return 401)."""
        app = create_app(config=APIConfig(auth_mode="api_key", api_key="test-secret-key-123"))
        client = TestClient(app)

        response = client.get(
            "/api/v1/symbols/search?q=RELIANCE",
            headers={"X-API-Key": "test-secret-key-123"},
        )
        # Should NOT be 401 (auth error)
        # May be 200, 500, or 503 depending on service state
        assert response.status_code != 401

    def test_order_endpoints_require_auth(self):
        """Order endpoints should be protected."""
        app = create_app(config=APIConfig(auth_mode="api_key", api_key="test-secret-key-123"))
        client = TestClient(app)

        response = client.get("/api/v1/orders")
        assert response.status_code == 401

        response = client.post("/api/v1/orders", json={})
        assert response.status_code == 401
