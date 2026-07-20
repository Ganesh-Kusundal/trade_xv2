"""Tests for rate limiting middleware."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interface.api.config import APIConfig
from interface.api.main import create_app
from interface.api.middleware import RateLimitMiddleware, _SlidingWindowCounter


class TestSlidingWindowCounter:
    """Unit tests for the sliding window counter."""

    def test_allows_within_limit(self):
        counter = _SlidingWindowCounter(window_seconds=60.0)
        allowed, remaining = counter.is_allowed("ip1", max_requests=5)
        assert allowed is True
        assert remaining == 4

    def test_blocks_after_limit(self):
        counter = _SlidingWindowCounter(window_seconds=60.0)
        for _ in range(5):
            counter.is_allowed("ip1", max_requests=5)
        allowed, remaining = counter.is_allowed("ip1", max_requests=5)
        assert allowed is False
        assert remaining == 0

    def test_separate_keys_independent(self):
        counter = _SlidingWindowCounter(window_seconds=60.0)
        for _ in range(5):
            counter.is_allowed("ip1", max_requests=5)
        # ip2 should still be allowed
        allowed, remaining = counter.is_allowed("ip2", max_requests=5)
        assert allowed is True
        assert remaining == 4

    def test_window_expiry(self):
        counter = _SlidingWindowCounter(window_seconds=0.1)
        for _ in range(3):
            counter.is_allowed("ip1", max_requests=3)
        # Should be blocked now
        allowed, _ = counter.is_allowed("ip1", max_requests=3)
        assert allowed is False
        # Wait for window to expire
        time.sleep(0.15)
        allowed, remaining = counter.is_allowed("ip1", max_requests=3)
        assert allowed is True
        # After expiry, one slot used (the new call), two remain
        assert remaining == 2


class TestRateLimitMiddleware:
    """Integration tests for the rate limiting middleware."""

    def test_disabled_when_max_requests_zero(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=0, window_seconds=60.0)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        for _ in range(10):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_allows_within_limit(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60.0)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_blocks_after_limit(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=2, window_seconds=60.0)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        resp = client.get("/test")
        assert resp.status_code == 200
        resp = client.get("/test")
        assert resp.status_code == 429

    def test_429_response_body(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=1, window_seconds=60.0)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        client.get("/test")  # consume the limit
        resp = client.get("/test")
        assert resp.status_code == 429
        data = resp.json()
        assert "detail" in data
        assert "retry_after_seconds" in data
        assert resp.headers["Retry-After"] == "60"
        assert resp.headers["X-RateLimit-Limit"] == "1"
        assert resp.headers["X-RateLimit-Remaining"] == "0"

    def test_rate_limit_headers_on_success(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=5, window_seconds=60.0)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "5"
        assert resp.headers["X-RateLimit-Remaining"] == "4"

    def test_websocket_upgrade_bypasses_rate_limit(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=1, window_seconds=60.0)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        client = TestClient(app)
        # First request consumes the limit
        resp = client.get("/test")
        assert resp.status_code == 200
        # A WebSocket upgrade request should bypass rate limiting
        resp = client.get("/test", headers={"connection": "upgrade"})
        assert resp.status_code == 200

    def test_health_endpoints_bypass_rate_limit(self):
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=1, window_seconds=60.0)

        @app.get("/api/v1/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(app)
        # Health endpoints should bypass rate limiting
        for _ in range(5):
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200

    def test_rate_limit_default_is_100_per_minute(self):
        config = APIConfig(auth_mode="none")
        assert config.rate_limit_per_minute == 100


class TestRateLimitWithCreateApp:
    """Integration tests using the full create_app factory."""

    def test_health_endpoints_exempt_with_default_config(self):
        app = create_app(config=APIConfig(auth_mode="none"))
        client = TestClient(app)
        # Health endpoints bypass rate limiting even when enabled (default 100/min)
        for _ in range(5):
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200

    def test_rate_limit_active_when_configured(self):
        app = create_app(config=APIConfig(auth_mode="none", rate_limit_per_minute=2))
        client = TestClient(app)
        # Use non-exempt endpoint (503 is fine, middleware still runs)
        resp = client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 503
        resp = client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 503
        # Third should be rate limited
        resp = client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 429

    def test_retry_after_header_present(self):
        app = create_app(config=APIConfig(auth_mode="none", rate_limit_per_minute=1))
        client = TestClient(app)
        resp = client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 503
        resp = client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) == 60
