"""API authentication — API key validation and dependency injection.

Authentication modes:
- "none": No authentication (default for CLI/local dev)
- "api_key": Require X-API-Key header on all protected endpoints

Public endpoints (never require auth):
- /healthz, /readyz (health probes)
- /docs, /redoc, /openapi.json (API documentation)

Protected endpoints (require auth when AUTH_MODE=api_key):
- /api/v1/orders, /api/v1/portfolio, /api/v1/risk (trading)
- /api/v1/market, /api/v1/analytics, /api/v1/scanner (data)
- /api/v1/replay, /api/v1/backtest, /api/v1/strategy (analytics)
- WebSocket streams (/ws/*) when AUTH_MODE=api_key

Usage:
    from api.auth import require_auth, validate_ws_api_key

    @router.post("/orders", dependencies=[Depends(require_auth)])
    async def create_order(...):
        ...
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Header, HTTPException, WebSocket, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AUTH_MODE = os.getenv("AUTH_MODE", "none").lower()
API_KEY = os.getenv("API_KEY", "")

# Generate a default API key if not provided (for local dev)
if AUTH_MODE == "api_key" and not API_KEY:
    API_KEY = secrets.token_urlsafe(32)
    logger.warning(
        "AUTH_MODE=api_key but API_KEY not set. "
        "A temporary key was generated; set API_KEY explicitly in production."
    )

# ── Security Scheme ───────────────────────────────────────────────────────────

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,  # Don't auto-reject; we handle it manually
    scheme_name="API Key",
)

# ── Public Paths ──────────────────────────────────────────────────────────────

PUBLIC_PATHS = frozenset(
    {
        "/healthz",
        "/readyz",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def is_public_path(path: str) -> bool:
    """Check if a path should bypass authentication."""
    return path in PUBLIC_PATHS


def _validate_api_key_value(api_key: str | None) -> None:
    """Raise HTTPException if the API key is missing or invalid."""
    if AUTH_MODE != "api_key":
        return

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(api_key, API_KEY):
        logger.warning("Invalid API key attempt from client")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def reject_ws_if_unauthorized(websocket: WebSocket) -> bool:
    """Validate WebSocket API key. Returns True if connection should proceed."""
    if AUTH_MODE != "api_key":
        return True

    api_key = websocket.query_params.get("api_key")
    if not api_key:
        api_key = websocket.headers.get("x-api-key")

    if api_key and secrets.compare_digest(api_key, API_KEY):
        return True

    logger.warning("WebSocket connection rejected: invalid or missing API key")
    await websocket.accept()
    await websocket.close(code=1008, reason="Unauthorized")
    return False


# ── Authentication Dependency ─────────────────────────────────────────────────


async def require_auth(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency that validates API key.

    Raises HTTPException(401) if:
    - AUTH_MODE is "api_key" AND
    - X-API-Key header is missing OR invalid

    Does nothing if:
    - AUTH_MODE is "none" (or unrecognized)
    - Path is public (health, docs)
    """
    _validate_api_key_value(x_api_key)


# ── Utility Functions ─────────────────────────────────────────────────────────


def get_api_key() -> str:
    """Return the current API key (for CLI scripts to display)."""
    return API_KEY


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return AUTH_MODE == "api_key"
