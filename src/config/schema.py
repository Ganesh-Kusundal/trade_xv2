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

    @classmethod
    def from_env(cls) -> AppConfig:
        """Load configuration from environment variables.

        Reads env vars with ``TRADEX_`` prefix first, then falls back to
        legacy names (APP_ENV, XV2_LOG_LEVEL, REDIS_URL, etc.) for backward
        compatibility.
        """
        # Build kwargs from env, preferring TRADEX_ prefixed then legacy
        kwargs: dict[str, object] = {}

        # app_env: TRADEX_APP_ENV → APP_ENV
        kwargs["app_env"] = os.environ.get(
            "TRADEX_APP_ENV", os.environ.get("APP_ENV", "dev")
        )

        # log_level: TRADEX_LOG_LEVEL → XV2_LOG_LEVEL
        kwargs["log_level"] = os.environ.get(
            "TRADEX_LOG_LEVEL", os.environ.get("XV2_LOG_LEVEL", "INFO")
        )

        # debug: TRADEX_DEBUG → TRADEXV2_DEBUG
        debug_raw = os.environ.get(
            "TRADEX_DEBUG", os.environ.get("TRADEXV2_DEBUG", "")
        )
        kwargs["debug"] = debug_raw.lower() in ("1", "true", "yes") if debug_raw else False

        # redis_url: TRADEX_REDIS_URL → REDIS_URL
        kwargs["redis_url"] = os.environ.get(
            "TRADEX_REDIS_URL", os.environ.get("REDIS_URL")
        ) or None

        # api_host: TRADEX_API_HOST → API_HOST
        kwargs["api_host"] = os.environ.get(
            "TRADEX_API_HOST", os.environ.get("API_HOST", "127.0.0.1")
        )

        # api_port: TRADEX_API_PORT → API_PORT
        api_port_raw = os.environ.get(
            "TRADEX_API_PORT", os.environ.get("API_PORT", "8080")
        )
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

        return cls(**kwargs)


# Broker config lives in brokers/*/config/settings.py (G4 resolved)


@dataclass(frozen=True)
class ApiConfig:
    """API server configuration."""

    auth_mode: str = "none"
    api_key: str = ""


@dataclass(frozen=True)
class TradingConfig:
    """Trading runtime configuration."""

    orchestrator_dry_run: bool = True
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
    """Load API server configuration from environment variables."""
    return ApiConfig(
        auth_mode=os.environ.get("AUTH_MODE", "none"),
        api_key=os.environ.get("API_KEY", ""),
    )


def load_trading_config() -> TradingConfig:
    """Load trading runtime configuration from environment variables."""
    return TradingConfig(
        orchestrator_dry_run=_get_bool("ORCHESTRATOR_DRY_RUN", True),
        orchestrator_min_confidence=_get_float("ORCHESTRATOR_MIN_CONFIDENCE", 0.7),
        enable_intelligent_gateway=_get_bool("ENABLE_INTELLIGENT_GATEWAY"),
        skip_parity_gate=_get_bool("SKIP_PARITY_GATE"),
        smart_routing=_get_bool("TRADEX_SMART_ROUTING", True),
        primary_broker=os.environ.get("TRADEX_PRIMARY_BROKER", "dhan"),
    )
