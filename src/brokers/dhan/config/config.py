"""Dhan broker runtime configuration — dataclasses + loading.

Centralizes all configurable parameters for Dhan broker resilience patterns
and their loading from environment variables, .env files, and JSON files.

Design Principles:
  - Dataclasses for type safety and immutability
  - Environment variable overrides with DHAN_RESILIENCE_ prefix
  - Backwards compatibility with existing defaults
  - Clean separation of concerns (rate limits, retries, circuit breakers)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.endpoints import Dhan

logger = logging.getLogger(__name__)

# ── Default base URL ─────────────────────────────────────────────────────────
DEFAULT_BASE_URL = Dhan.REST_BASE


# ── Rate Limit Defaults (from Dhan API documentation) ────────────────────────
DEFAULT_RATE_LIMITS: dict[str, float] = {
    "/marketfeed/quote": 1.0,  # Quote APIs: 1 req/s
    "/marketfeed/ltp": 0.1,  # Data APIs: 10 req/s (0.1s interval)
    "/marketfeed/ohlc": 0.1,  # Data APIs: 10 req/s (0.1s interval)
    "/optionchain": 0.1,  # Data APIs: 10 req/s (0.1s interval)
    "/charts/": 0.1,  # Data APIs: 10 req/s (0.1s interval)
    "/orders": 0.04,  # Order APIs: 25 req/s (0.04s interval)
    "/positions": 0.05,  # Non-Trading APIs: 20 req/s (0.05s interval)
    "/holdings": 0.05,  # Non-Trading APIs: 20 req/s (0.05s interval)
    "/fundlimit": 0.05,  # Non-Trading APIs: 20 req/s (0.05s interval)
}


# ── Circuit Breaker Prefixes ────────────────────────────────────────────────

DEFAULT_READ_CB_PREFIXES: tuple[str, ...] = (
    "/marketfeed/ltp",
    "/marketfeed/quote",
    "/marketfeed/ohlc",
    "/charts/",
    "/optionchain",
    "/marketstatus",
    "/instruments",
)

DEFAULT_WRITE_CB_PREFIXES: tuple[str, ...] = (
    "/orders",
    "/killswitch",
    "/sliceorder",
)

# Legacy CB-category → RL-bucket map (prefer path-based mapping in http_client).
DEFAULT_RL_BUCKET_MAP: dict[str, str] = {
    "read": "quotes",
    "write": "orders",
    "admin": "admin",
}


# ── Retry Configuration Defaults ────────────────────────────────────────────
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 500
DEFAULT_MAX_DELAY_MS = 5000


# ── Token Refresh Configuration ──────────────────────────────────────────────
DEFAULT_REFRESH_COOLDOWN_SECONDS = 60
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 130  # Dhan's 2-min rate limit + 10s buffer


# ── Env var loading ──────────────────────────────────────────────────────────

ENV_PREFIX = "DHAN_RESILIENCE_"

ENV_KEY_MAPPING: dict[str, str] = {
    "RATE_LIMIT_LIMITS": "rate_limit.limits",
    "RATE_LIMIT_READ_PREFIXES": "rate_limit.read_prefixes",
    "RATE_LIMIT_WRITE_PREFIXES": "rate_limit.write_prefixes",
    "RATE_LIMIT_BUCKET_MAP": "rate_limit.bucket_map",
    "RETRY_MAX_RETRIES": "retry.max_retries",
    "RETRY_BASE_DELAY_MS": "retry.base_delay_ms",
    "RETRY_MAX_DELAY_MS": "retry.max_delay_ms",
    "CB_READ_PREFIXES": "circuit_breaker.read_prefixes",
    "CB_WRITE_PREFIXES": "circuit_breaker.write_prefixes",
    "CB_ORDERS_FAILURE_THRESHOLD": "circuit_breaker.orders_failure_threshold",
    "CB_DEFAULT_FAILURE_THRESHOLD": "circuit_breaker.default_failure_threshold",
    "CB_RECOVERY_TIMEOUT_MS": "circuit_breaker.recovery_timeout_ms",
    "CB_SUCCESS_THRESHOLD": "circuit_breaker.success_threshold",
    "TOKEN_REFRESH_COOLDOWN_SECONDS": "token.refresh_cooldown_seconds",
    "TOKEN_RATE_LIMIT_BACKOFF_SECONDS": "token.rate_limit_backoff_seconds",
    "BASE_URL": "base_url",
}


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DhanRateLimitConfig:
    """Configuration for Dhan API rate limiting."""

    limits: dict[str, float] = field(default_factory=lambda: DEFAULT_RATE_LIMITS.copy())
    read_prefixes: tuple[str, ...] = DEFAULT_READ_CB_PREFIXES
    write_prefixes: tuple[str, ...] = DEFAULT_WRITE_CB_PREFIXES
    bucket_map: dict[str, str] = field(default_factory=lambda: DEFAULT_RL_BUCKET_MAP.copy())

    def get_endpoint_interval(self, endpoint: str) -> float:
        if endpoint in self.limits:
            return self.limits[endpoint]
        for prefix, interval in self.limits.items():
            if endpoint.startswith(prefix):
                return interval
        return 0


@dataclass(frozen=True)
class DhanRetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS
    max_delay_ms: int = DEFAULT_MAX_DELAY_MS


@dataclass(frozen=True)
class DhanCircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    read_prefixes: tuple[str, ...] = DEFAULT_READ_CB_PREFIXES
    write_prefixes: tuple[str, ...] = DEFAULT_WRITE_CB_PREFIXES
    orders_failure_threshold: int = 3
    default_failure_threshold: int = 5
    recovery_timeout_ms: int = 30_000
    success_threshold: int = 3

    def categorize_endpoint(self, endpoint: str) -> str:
        for prefix in self.write_prefixes:
            if endpoint.startswith(prefix):
                return "write"
        for prefix in self.read_prefixes:
            if endpoint.startswith(prefix):
                return "read"
        return "admin"


@dataclass(frozen=True)
class DhanTokenConfig:
    """Configuration for token refresh behavior."""

    refresh_cooldown_seconds: float = DEFAULT_REFRESH_COOLDOWN_SECONDS
    rate_limit_backoff_seconds: float = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS


@dataclass(frozen=True)
class DhanResilienceConfig:
    """Aggregated configuration for all Dhan resilience patterns."""

    rate_limit: DhanRateLimitConfig = field(default_factory=DhanRateLimitConfig)
    retry: DhanRetryConfig = field(default_factory=DhanRetryConfig)
    circuit_breaker: DhanCircuitBreakerConfig = field(default_factory=DhanCircuitBreakerConfig)
    token: DhanTokenConfig = field(default_factory=DhanTokenConfig)
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> DhanResilienceConfig:
        if data is None:
            return cls()

        rate_limit_data = data.get("rate_limit", {})
        retry_data = data.get("retry", {})
        circuit_breaker_data = data.get("circuit_breaker", {})
        token_data = data.get("token", {})

        return cls(
            rate_limit=DhanRateLimitConfig(
                limits=rate_limit_data.get("limits", DEFAULT_RATE_LIMITS.copy()),
                read_prefixes=tuple(rate_limit_data.get("read_prefixes", DEFAULT_READ_CB_PREFIXES)),
                write_prefixes=tuple(
                    rate_limit_data.get("write_prefixes", DEFAULT_WRITE_CB_PREFIXES)
                ),
                bucket_map=rate_limit_data.get("bucket_map", DEFAULT_RL_BUCKET_MAP.copy()),
            ),
            retry=DhanRetryConfig(
                max_retries=retry_data.get("max_retries", DEFAULT_MAX_RETRIES),
                base_delay_ms=retry_data.get("base_delay_ms", DEFAULT_BASE_DELAY_MS),
                max_delay_ms=retry_data.get("max_delay_ms", DEFAULT_MAX_DELAY_MS),
            ),
            circuit_breaker=DhanCircuitBreakerConfig(
                read_prefixes=tuple(
                    circuit_breaker_data.get("read_prefixes", DEFAULT_READ_CB_PREFIXES)
                ),
                write_prefixes=tuple(
                    circuit_breaker_data.get("write_prefixes", DEFAULT_WRITE_CB_PREFIXES)
                ),
                orders_failure_threshold=circuit_breaker_data.get("orders_failure_threshold", 3),
                default_failure_threshold=circuit_breaker_data.get("default_failure_threshold", 5),
                recovery_timeout_ms=circuit_breaker_data.get("recovery_timeout_ms", 30_000),
                success_threshold=circuit_breaker_data.get("success_threshold", 3),
            ),
            token=DhanTokenConfig(
                refresh_cooldown_seconds=token_data.get(
                    "refresh_cooldown_seconds", DEFAULT_REFRESH_COOLDOWN_SECONDS
                ),
                rate_limit_backoff_seconds=token_data.get(
                    "rate_limit_backoff_seconds", DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
                ),
            ),
            base_url=data.get("base_url", DEFAULT_BASE_URL),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rate_limit": {
                "limits": self.rate_limit.limits,
                "read_prefixes": list(self.rate_limit.read_prefixes),
                "write_prefixes": list(self.rate_limit.write_prefixes),
                "bucket_map": self.rate_limit.bucket_map,
            },
            "retry": {
                "max_retries": self.retry.max_retries,
                "base_delay_ms": self.retry.base_delay_ms,
                "max_delay_ms": self.retry.max_delay_ms,
            },
            "circuit_breaker": {
                "read_prefixes": list(self.circuit_breaker.read_prefixes),
                "write_prefixes": list(self.circuit_breaker.write_prefixes),
                "orders_failure_threshold": self.circuit_breaker.orders_failure_threshold,
                "default_failure_threshold": self.circuit_breaker.default_failure_threshold,
                "recovery_timeout_ms": self.circuit_breaker.recovery_timeout_ms,
                "success_threshold": self.circuit_breaker.success_threshold,
            },
            "token": {
                "refresh_cooldown_seconds": self.token.refresh_cooldown_seconds,
                "rate_limit_backoff_seconds": self.token.rate_limit_backoff_seconds,
            },
            "base_url": self.base_url,
        }


# ── Default instance ─────────────────────────────────────────────────────────
DEFAULT_CONFIG = DhanResilienceConfig()


# ── Loading helpers (merged from config_loader.py) ───────────────────────────


def _parse_env_value(value: str, target_type: type) -> Any:
    if target_type == bool:
        return value.lower() in ("true", "1", "yes", "on")
    if target_type == int:
        return int(value)
    if target_type == float:
        return float(value)
    if target_type == dict:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    if target_type == list:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [v.strip() for v in value.split(",") if v.strip()]
    if target_type == tuple:
        try:
            parsed = json.loads(value)
            return tuple(parsed) if isinstance(parsed, list) else ()
        except json.JSONDecodeError:
            return tuple(v.strip() for v in value.split(",") if v.strip())
    return value


def _parse_json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return [v.strip() for v in value.split(",") if v.strip()]


def _parse_json_dict(value: str) -> dict[str, float]:
    try:
        parsed = json.loads(value)
        return {str(k): float(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _flatten_env_vars(prefix: str = ENV_PREFIX) -> dict[str, str]:
    result = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            result[key[len(prefix) :]] = value
    return result


def _build_nested_dict(flat_data: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for env_key, value in flat_data.items():
        if env_key not in ENV_KEY_MAPPING:
            continue

        path = ENV_KEY_MAPPING[env_key]
        keys = path.split(".")

        current = result
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        final_key = keys[-1]

        if final_key == "limits":
            current[final_key] = _parse_json_dict(value)
        elif final_key in ("read_prefixes", "write_prefixes"):
            current[final_key] = _parse_json_list(value)
        elif final_key == "bucket_map":
            current[final_key] = _parse_json_dict(value)
        elif final_key in (
            "max_retries",
            "orders_failure_threshold",
            "default_failure_threshold",
            "success_threshold",
            "recovery_timeout_ms",
            "base_delay_ms",
            "max_delay_ms",
        ):
            current[final_key] = int(value)
        elif final_key in ("refresh_cooldown_seconds", "rate_limit_backoff_seconds"):
            current[final_key] = float(value)
        elif final_key == "base_url":
            current[final_key] = value
        else:
            current[final_key] = value

    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _parse_env_file(env_path: Path) -> dict[str, str]:
    result = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


# ── Public loading functions ─────────────────────────────────────────────────


def load_from_environment(prefix: str = ENV_PREFIX) -> DhanResilienceConfig:
    flat_vars = _flatten_env_vars(prefix)
    nested_data = _build_nested_dict(flat_vars)
    return DhanResilienceConfig.from_dict(nested_data)


def load_from_file(file_path: Path) -> DhanResilienceConfig:
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    return DhanResilienceConfig.from_dict(data)


def load_from_env_file(env_path: Path | None = None) -> DhanResilienceConfig:
    data: dict[str, Any] = {}

    paths_to_try = []
    if env_path:
        paths_to_try.append(env_path)
    paths_to_try.extend([Path(".env.local"), Path(".env")])

    for path in paths_to_try:
        if path.exists():
            try:
                data.update(_parse_env_file(path))
            except Exception as e:
                logger.warning(f"Failed to parse env file {path}: {e}")

    env_data = _build_nested_dict(_flatten_env_vars(ENV_PREFIX))
    data = _deep_merge(data, env_data)

    return DhanResilienceConfig.from_dict(data)


class DhanConfigLoader:
    """Configuration loader with fallback chain: env vars > .env file > defaults."""

    @staticmethod
    def load(
        env_path: Path | None = None,
        env_prefix: str = ENV_PREFIX,
    ) -> DhanResilienceConfig:
        env_file_data: dict[str, Any] = {}
        paths_to_try = [env_path] if env_path else [Path(".env.local"), Path(".env")]
        for path in paths_to_try:
            if path and path.exists():
                try:
                    env_file_data.update(_parse_env_file(path))
                except Exception as e:
                    logger.warning(f"Failed to parse env file {path}: {e}")

        nested_env_data = _build_nested_dict(env_file_data)
        env_var_data = _build_nested_dict(_flatten_env_vars(env_prefix))
        merged_data = _deep_merge(nested_env_data, env_var_data)

        return DhanResilienceConfig.from_dict(merged_data)

    @staticmethod
    def load_from_file(file_path: Path) -> DhanResilienceConfig:
        return load_from_file(file_path)

    @staticmethod
    def load_from_dict(data: dict[str, Any]) -> DhanResilienceConfig:
        return DhanResilienceConfig.from_dict(data)

    @staticmethod
    def load_from_environment(prefix: str = ENV_PREFIX) -> DhanResilienceConfig:
        return load_from_environment(prefix)


__all__ = [
    "DEFAULT_BASE_DELAY_MS",
    "DEFAULT_CONFIG",
    "DEFAULT_MAX_DELAY_MS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RATE_LIMITS",
    "DEFAULT_RATE_LIMIT_BACKOFF_SECONDS",
    "DEFAULT_READ_CB_PREFIXES",
    "DEFAULT_REFRESH_COOLDOWN_SECONDS",
    "DEFAULT_RL_BUCKET_MAP",
    "DEFAULT_WRITE_CB_PREFIXES",
    "ENV_KEY_MAPPING",
    "ENV_PREFIX",
    "DhanCircuitBreakerConfig",
    "DhanConfigLoader",
    "DhanRateLimitConfig",
    "DhanResilienceConfig",
    "DhanRetryConfig",
    "DhanTokenConfig",
    "load_from_env_file",
    "load_from_environment",
    "load_from_file",
]
