"""API authentication — API key validation and dependency injection.

Authentication modes:
- ``api_key``: Require X-API-Key header on all protected endpoints (default).

Any other ``AUTH_MODE`` value is rejected at startup and on every request
(fail-closed — no silent unauthenticated trading surface).

Public endpoints (never require auth in development):
- /healthz, /readyz (health probes)

In production/staging (``TRADEX_ENV``), /docs, /redoc, /openapi.json also require auth.

Control-plane routes (kill-switch) require ``ADMIN_API_KEY`` (or ``API_KEY`` in dev
when ``ADMIN_API_KEY`` is unset).
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Header, HTTPException, WebSocket, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_VALID_AUTH_MODES = frozenset({"api_key"})


def _auth_none_allowed() -> bool:
    """``none`` auth is test-only — never in production."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    return env not in ("production", "staging") and os.getenv("TRADEX_ALLOW_AUTH_NONE") == "1"


def _normalize_auth_mode(mode: str) -> str:
    m = mode.lower().strip()
    if m == "none":
        if not _auth_none_allowed():
            raise RuntimeError(
                "AUTH_MODE='none' is forbidden outside tests/local dev "
                "(set TRADEX_ALLOW_AUTH_NONE=1 for explicit local opt-in)"
            )
        return m
    if m not in _VALID_AUTH_MODES:
        raise RuntimeError(
            f"Invalid AUTH_MODE={m!r}. Only 'api_key' is permitted (fail-closed)."
        )
    return m

# ── Configuration ─────────────────────────────────────────────────────────────

AUTH_MODE: str = _normalize_auth_mode(os.getenv("AUTH_MODE", "api_key"))
API_KEY: str = os.getenv("API_KEY", "")
ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")

if AUTH_MODE == "api_key" and not API_KEY:
    API_KEY = secrets.token_urlsafe(32)
    logger.warning(
        "AUTH_MODE=api_key but API_KEY not set. "
        "A temporary key was generated; set API_KEY explicitly in production."
    )


def configure(*, auth_mode: str, api_key: str = "") -> None:
    """Override auth settings from APIConfig (called by ``create_app``)."""
    global AUTH_MODE, API_KEY
    AUTH_MODE = _normalize_auth_mode(auth_mode)
    if api_key:
        API_KEY = api_key
    elif AUTH_MODE == "api_key" and not API_KEY:
        API_KEY = secrets.token_urlsafe(32)


def _is_production_docs_gated() -> bool:
    """Gate OpenAPI/docs behind auth in production/staging."""
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    return env in ("production", "staging")


# ── Security Scheme ───────────────────────────────────────────────────────────

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="API Key",
)

# ── Public Paths ──────────────────────────────────────────────────────────────

_BASE_PUBLIC_PATHS = frozenset(
    {
        "/healthz",
        "/readyz",
    }
)

_DEV_PUBLIC_PATHS = frozenset(
    {
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/healthz",
        "/readyz",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def is_public_path(path: str) -> bool:
    """Check if a path should bypass authentication."""
    if path in _BASE_PUBLIC_PATHS:
        return True
    if not _is_production_docs_gated() and path in _DEV_PUBLIC_PATHS:
        return True
    return False


def _validate_api_key_value(api_key: str | None) -> None:
    """Raise HTTPException if the API key is missing or invalid (fail-closed)."""
    if AUTH_MODE == "none":
        return

    if AUTH_MODE not in _VALID_AUTH_MODES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication misconfigured (invalid AUTH_MODE)",
        )

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


def _validate_admin_api_key(api_key: str | None) -> None:
    """Require admin credentials for control-plane routes."""
    _validate_api_key_value(api_key)
    admin_key = (ADMIN_API_KEY or os.getenv("ADMIN_API_KEY", "")).strip()
    if admin_key:
        if not api_key or not secrets.compare_digest(api_key, admin_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin API key required for this operation",
            )
        return
    # Dev fallback: primary API_KEY is admin when ADMIN_API_KEY unset
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    if env in ("production", "staging"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY must be set in production for control-plane routes",
        )


async def reject_ws_if_unauthorized(websocket: WebSocket) -> bool:
    """Validate WebSocket API key via header only (never query string)."""
    if AUTH_MODE == "none":
        return True

    if AUTH_MODE not in _VALID_AUTH_MODES:
        await websocket.accept()
        await websocket.close(code=1008, reason="Auth misconfigured")
        return False

    api_key = websocket.headers.get("x-api-key")

    if api_key and secrets.compare_digest(api_key, API_KEY):
        return True

    logger.warning("WebSocket connection rejected: invalid or missing API key")
    await websocket.accept()
    await websocket.close(code=1008, reason="Unauthorized")
    return False


async def require_auth(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency that validates API key."""
    _validate_api_key_value(x_api_key)


async def require_admin(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency for control-plane routes (kill-switch, etc.)."""
    _validate_admin_api_key(x_api_key)


def get_api_key() -> str:
    """Return the current API key (for CLI scripts to display)."""
    return API_KEY


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return AUTH_MODE == "api_key"
