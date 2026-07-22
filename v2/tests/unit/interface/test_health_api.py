"""Health API — /health/live returns 200."""

from __future__ import annotations

from interface.api.app import create_app


def test_health_live_returns_200() -> None:
    app = create_app()
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        if isinstance(app, FastAPI):
            resp = TestClient(app).get("/health/live")
            assert resp.status_code == 200
            return
    except ImportError:
        pass

    status, _body = app.request("GET", "/health/live")  # type: ignore[attr-defined]
    assert status == 200
