"""FastAPI health endpoints."""

from __future__ import annotations

from typing import Any


def create_app() -> Any:
    from fastapi import FastAPI

    app = FastAPI(title="TradeX", version="0.1.0")

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok", "check": "live"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ok", "check": "ready"}

    return app
