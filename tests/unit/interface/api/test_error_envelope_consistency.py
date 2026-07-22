"""WS-I: API error responses use a consistent ``{"error": {...}}`` envelope."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from infrastructure.global_exception_handler import setup_exception_handlers
from interface.api.middleware import RateLimitMiddleware


def test_http_exception_uses_error_envelope():
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Live orders blocked")

    client = TestClient(app)
    resp = client.get("/forbidden")
    assert resp.status_code == 403
    data = resp.json()
    assert "error" in data
    assert data["error"]["type"] == "http_error"
    assert data["error"]["message"] == "Live orders blocked"
    assert data["error"]["status_code"] == 403
    assert data["error"]["details"] == {}


def test_rate_limit_middleware_uses_error_envelope():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=1, window_seconds=60.0)

    @app.get("/test")
    async def handler():
        return {"ok": True}

    client = TestClient(app)
    client.get("/test")
    resp = client.get("/test")
    assert resp.status_code == 429
    data = resp.json()
    assert "error" in data
    assert data["error"]["type"] == "rate_limit_exceeded"
    assert data["error"]["status_code"] == 429
    assert data["error"]["details"]["retry_after"] == 60
    assert resp.headers["Retry-After"] == "60"
