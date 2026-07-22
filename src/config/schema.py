"""Central configuration schema for TradeXV2.

Defines typed defaults for all *application-level* environment variables.
Operators should set values in .env.local; this module provides the schema
and defaults so every consumer has a single source of truth.

This module handles: app_env, log_level, redis, API server ports, rate limiting.
Broker-specific config (credentials, endpoints, timeouts) lives in
``brokers/*/config/settings.py`` via ``SettingsLoaderBase`` — see G4 resolution.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class AppConfig(BaseModel):
    """Central application configuration with env-var loading.

    All fields map to environment variables. Use ``AppConfig.from_env()``
    to load from the current environment, or construct directly for testing.
    """

    # ── Core ────────────────────────────────────────────────
    app_env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    debug: bool = False
    redis_url: str | None = None

    # ── API Server ──────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    observability_port: int = 8765
    cors_origins: list[str] = ["http://localhost:5173"]

    # ── Rate Limiting ───────────────────────────────────────
    rate_limit_max_requests: int = 0
    rate_limit_window_seconds: float = 60.0

    # ── API Security & Auth ─────────────────────────────────
    auth_mode: str = "none"
    api_key: str = ""

    # ── CORS Details ────────────────────────────────────────
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = [
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS",
    ]
    cors_allow_headers: list[str] = [
        "Authorization",
        "Content-Type",
        "X-Correlation-ID",
        "X-API-Key",
    ]

    # ── Pagination ──────────────────────────────────────────
    max_page_size: int = 1000
    default_page_size: int = 100

    # ── API Routing ─────────────────────────────────────────
    api_prefix: str = "/api/v1"

    # ── Trading runtime (ADR-003) ───────────────────────────
    orchestrator_dry_run: bool = False
    orchestrator_min_confidence: float = 0.7
    enable_intelligent_gateway: bool = False
    skip_parity_gate: bool = False
    smart_routing: bool = True
    primary_broker: str = "dhan"
    risk_fail_open: bool = False

    model_config = {"env_prefix": "TRADEX_", "env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log level '{v}'. Must be one of: {sorted(_VALID_LOG_LEVELS)}"
            )
        return upper

    @field_validator("api_port", "observability_port")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"Port must be > 0, got {v}")
        return v

    def is_production_or_staging(self) -> bool:
        """True when strict production boot validation must run."""
        tradex_env = (os.environ.get("TRADEX_ENV") or "").strip().lower()
        if tradex_env in ("production", "staging"):
            return True
        return self.app_env in ("prod", "staging")

    @classmethod
    def from_env(cls) -> AppConfig:
        """Load configuration from environment variables.

        Reads env vars with ``TRADEX_`` prefix first, then falls back to
        legacy names (APP_ENV, XV2_LOG_LEVEL, REDIS_URL, etc.) for backward
        compatibility.
        """
        # Build kwargs from env, preferring TRADEX_ prefixed then legacy
        kwargs: dict[str, object] = {}

        # app_env: TRADEX_APP_ENV → APP_ENV → TRADEX_ENV (production→prod)
        app_env_raw = os.environ.get("TRADEX_APP_ENV") or os.environ.get("APP_ENV")
        if not app_env_raw:
            tradex_env = (os.environ.get("TRADEX_ENV") or "development").strip().lower()
            if tradex_env in ("production", "prod"):
                app_env_raw = "prod"
            elif tradex_env == "staging":
                app_env_raw = "staging"
            else:
                app_env_raw = "dev"
        kwargs["app_env"] = app_env_raw

        # log_level: TRADEX_LOG_LEVEL → XV2_LOG_LEVEL
        kwargs["log_level"] = os.environ.get(
            "TRADEX_LOG_LEVEL", os.environ.get("XV2_LOG_LEVEL", "INFO")
        )

        # debug: TRADEX_DEBUG → TRADEXV2_DEBUG
        debug_raw = os.environ.get("TRADEX_DEBUG", os.environ.get("TRADEXV2_DEBUG", ""))
        kwargs["debug"] = debug_raw.lower() in ("1", "true", "yes") if debug_raw else False

        # redis_url: TRADEX_REDIS_URL → REDIS_URL
        kwargs["redis_url"] = (
            os.environ.get("TRADEX_REDIS_URL", os.environ.get("REDIS_URL")) or None
        )

        # api_host: TRADEX_API_HOST → API_HOST
        kwargs["api_host"] = os.environ.get(
            "TRADEX_API_HOST", os.environ.get("API_HOST", "127.0.0.1")
        )

        # api_port: TRADEX_API_PORT → API_PORT
        api_port_raw = os.environ.get("TRADEX_API_PORT", os.environ.get("API_PORT", "8080"))
        kwargs["api_port"] = int(api_port_raw)

        # observability_port
        obs_raw = os.environ.get("TRADEX_OBSERVABILITY_PORT", "8765")
        kwargs["observability_port"] = int(obs_raw)

        # cors_origins: comma-separated
        cors_raw = os.environ.get("TRADEX_CORS_ORIGINS", "")
        if cors_raw:
            kwargs["cors_origins"] = [o.strip() for o in cors_raw.split(",") if o.strip()]

        # rate_limit_max_requests
        rl_raw = os.environ.get("TRADEX_RATE_LIMIT_MAX_REQUESTS", "0")
        kwargs["rate_limit_max_requests"] = int(rl_raw)

        # rate_limit_window_seconds
        rw_raw = os.environ.get("TRADEX_RATE_LIMIT_WINDOW_SECONDS", "60.0")
        kwargs["rate_limit_window_seconds"] = float(rw_raw)

        # auth_mode: TRADEX_AUTH_MODE → AUTH_MODE
        kwargs["auth_mode"] = os.environ.get(
            "TRADEX_AUTH_MODE", os.environ.get("AUTH_MODE", "none")
        )

        # api_key: TRADEX_API_KEY → API_KEY
        kwargs["api_key"] = os.environ.get(
            "TRADEX_API_KEY", os.environ.get("API_KEY", "")
        )

        # cors_allow_credentials
        cac_raw = os.environ.get("TRADEX_CORS_ALLOW_CREDENTIALS", "true")
        kwargs["cors_allow_credentials"] = cac_raw.lower() in ("1", "true", "yes")

        # cors_allow_methods: comma-separated
        cam_raw = os.environ.get("TRADEX_CORS_ALLOW_METHODS", "")
        if cam_raw:
            kwargs["cors_allow_methods"] = [m.strip() for m in cam_raw.split(",") if m.strip()]

        # cors_allow_headers: comma-separated
        cah_raw = os.environ.get("TRADEX_CORS_ALLOW_HEADERS", "")
        if cah_raw:
            kwargs["cors_allow_headers"] = [h.strip() for h in cah_raw.split(",") if h.strip()]

        # max_page_size
        mps_raw = os.environ.get("TRADEX_MAX_PAGE_SIZE", "1000")
        kwargs["max_page_size"] = int(mps_raw)

        # default_page_size
        dps_raw = os.environ.get("TRADEX_DEFAULT_PAGE_SIZE", "100")
        kwargs["default_page_size"] = int(dps_raw)

        # api_prefix
        kwargs["api_prefix"] = os.environ.get("TRADEX_API_PREFIX", "/api/v1")

        # trading runtime
        kwargs["orchestrator_dry_run"] = _first_env_bool(
            "TRADEX_ORCHESTRATOR_DRY_RUN", "ORCHESTRATOR_DRY_RUN", default=False
        )
        kwargs["orchestrator_min_confidence"] = _first_env_float(
            "TRADEX_ORCHESTRATOR_MIN_CONFIDENCE",
            "ORCHESTRATOR_MIN_CONFIDENCE",
            default=0.7,
        )
        kwargs["enable_intelligent_gateway"] = _first_env_bool(
            "TRADEX_ENABLE_INTELLIGENT_GATEWAY", "ENABLE_INTELLIGENT_GATEWAY"
        )
        kwargs["skip_parity_gate"] = _first_env_bool(
            "TRADEX_SKIP_PARITY_GATE", "SKIP_PARITY_GATE"
        )
        kwargs["smart_routing"] = _first_env_bool(
            "TRADEX_SMART_ROUTING", default=True
        )
        kwargs["primary_broker"] = os.environ.get(
            "TRADEX_PRIMARY_BROKER", "dhan"
        ).strip() or "dhan"
        kwargs["risk_fail_open"] = _first_env_bool(
            "TRADEX_RISK_FAIL_OPEN", "RISK_FAIL_OPEN"
        )

        return cls(**kwargs)


def _first_env_bool(*keys: str, default: bool = False) -> bool:
    for key in keys:
        raw = os.environ.get(key, "")
        if raw:
            return raw.lower() in ("1", "true", "yes")
    return default


def _first_env_float(*keys: str, default: float = 0.0) -> float:
    for key in keys:
        raw = os.environ.get(key, "")
        if raw:
            try:
                return float(raw)
            except ValueError:
                return default
    return default


# Broker config lives in brokers/*/config/settings.py (G4 resolved)


@dataclass(frozen=True)
class ApiConfig:
    """API server configuration."""

    auth_mode: str = "none"
    api_key: str = ""


@dataclass(frozen=True)
class TradingConfig:
    """Trading runtime configuration."""

    orchestrator_dry_run: bool = False
    orchestrator_min_confidence: float = 0.7
    enable_intelligent_gateway: bool = False
    skip_parity_gate: bool = False
    smart_routing: bool = True  # Enable intelligent routing by default
    primary_broker: str = "dhan"


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "")
    if not val:
        return default
    return val.lower() in ("1", "true", "yes")


def _get_int(key: str, default: int = 0) -> int:
    val = os.environ.get(key, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_float(key: str, default: float = 0.0) -> float:
    val = os.environ.get(key, "")
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def load_api_config() -> ApiConfig:
    """Load API server configuration from AppConfig (ADR-003)."""
    cfg = AppConfig.from_env()
    return ApiConfig(auth_mode=cfg.auth_mode, api_key=cfg.api_key)


def load_trading_config() -> TradingConfig:
    """Load trading runtime configuration from AppConfig (ADR-003)."""
    cfg = AppConfig.from_env()
    return TradingConfig(
        orchestrator_dry_run=cfg.orchestrator_dry_run,
        orchestrator_min_confidence=cfg.orchestrator_min_confidence,
        enable_intelligent_gateway=cfg.enable_intelligent_gateway,
        skip_parity_gate=cfg.skip_parity_gate,
        smart_routing=cfg.smart_routing,
        primary_broker=cfg.primary_broker,
    )
