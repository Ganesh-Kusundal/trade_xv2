"""Health HTTP surface — FastAPI if installed, else stdlib http.server."""

from __future__ import annotations

import json
from typing import Any


def _health_payload(kind: str) -> dict[str, str]:
    return {"status": "ok", "check": kind}


def _make_fastapi_app() -> Any:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="TradeX", version="0.1.0")

    @app.get("/health/live")
    def live() -> JSONResponse:
        return JSONResponse(_health_payload("live"))

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        return JSONResponse(_health_payload("ready"))

    return app


class HealthApp:
    """Minimal stdlib health server (no FastAPI)."""

    def request(self, method: str, path: str) -> tuple[int, bytes]:
        if method.upper() != "GET":
            return 405, json.dumps({"status": "method_not_allowed"}).encode()
        if path == "/health/live":
            return 200, json.dumps(_health_payload("live")).encode()
        if path == "/health/ready":
            return 200, json.dumps(_health_payload("ready")).encode()
        return 404, json.dumps({"status": "not_found"}).encode()

    def serve_forever(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        from http.server import BaseHTTPRequestHandler, HTTPServer

        app = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                status, body = app.request("GET", self.path)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

        HTTPServer((host, port), Handler).serve_forever()


def create_app() -> Any:
    try:
        return _make_fastapi_app()
    except ImportError:
        return HealthApp()


# module-level app for uvicorn / ASGI entry
app = create_app()
