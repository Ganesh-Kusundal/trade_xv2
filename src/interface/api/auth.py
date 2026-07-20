"""API authentication — optional API key validation.

Default ``AUTH_MODE=none`` (no ``X-API-Key`` required). Set ``AUTH_MODE=api_key``
and ``API_KEY`` only if you expose the API beyond localhost.

Public endpoints (never require auth):
- /healthz, /readyz (health probes)
- /api/v1/health/metrics (observability)
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Header, HTTPException, WebSocket, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_VALID_AUTH_MODES = frozenset({"none", "api_key"})


def _normalize_auth_mode(mode: str) -> str:
    m = mode.lower().strip()
    if m not in _VALID_AUTH_MODES:
        raise RuntimeError(
            f"Invalid AUTH_MODE={m!r}. Use 'none' (default) or 'api_key'."
        )
    return m

# ── Configuration ─────────────────────────────────────────────────────────────


class _AuthConfig:
    """Module-level auth configuration state."""

    AUTH_MODE: str = _normalize_auth_mode(os.getenv("AUTH_MODE", "none"))
    API_KEY: str = os.getenv("API_KEY", "")
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")

    @classmethod
    def configure(cls, *, auth_mode: str, api_key: str = "") -> None:
        """Override auth settings from APIConfig (called by ``create_app``)."""
        cls.AUTH_MODE = _normalize_auth_mode(auth_mode)
        if api_key:
            cls.API_KEY = api_key.strip()
        elif cls.AUTH_MODE == "api_key" and not cls.API_KEY:
            cls.API_KEY = secrets.token_urlsafe(32)
            logger.warning(
                "AUTH_MODE=api_key but API_KEY not set — ephemeral key generated."
            )
        elif cls.AUTH_MODE == "none":
            cls.API_KEY = ""


AUTH_MODE = _AuthConfig.AUTH_MODE  # intentional module singleton — read by FastAPI deps
API_KEY = _AuthConfig.API_KEY  # intentional module singleton — read by FastAPI deps
ADMIN_API_KEY = _AuthConfig.ADMIN_API_KEY

if AUTH_MODE == "api_key" and not API_KEY.strip():
    API_KEY = secrets.token_urlsafe(32)
    _AuthConfig.API_KEY = API_KEY
    logger.warning(
        "AUTH_MODE=api_key but API_KEY not set — ephemeral key generated."
    )


def configure(*, auth_mode: str, api_key: str = "") -> None:
    """Override auth settings from APIConfig (called by ``create_app``)."""
    _AuthConfig.configure(auth_mode=auth_mode, api_key=api_key)
    global AUTH_MODE, API_KEY  # intentional module singleton — updated once at startup
    AUTH_MODE = _AuthConfig.AUTH_MODE
    API_KEY = _AuthConfig.API_KEY


def _is_production_docs_gated() -> bool:
    """Gate OpenAPI/docs behind auth when api_key mode + production env."""
    if AUTH_MODE != "api_key":
        return False
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
    """Raise HTTPException if the API key is missing or invalid."""
    if AUTH_MODE == "none":
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


async def reject_ws_if_unauthorized(websocket: WebSocket) -> bool:
    """Validate WebSocket API key via header only (never query string)."""
    if AUTH_MODE == "none":
        return True

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
    """FastAPI dependency that validates API key when AUTH_MODE=api_key."""
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
