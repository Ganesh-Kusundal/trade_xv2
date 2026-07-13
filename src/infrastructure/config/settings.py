"""Broker settings — base dataclass + base loader for broker-specific config.

Intentional separation from :mod:`config.schema` (``AppConfig``):

* ``AppConfig`` = application-level configuration (env, log_level, redis,
  API server ports, rate limiting).  Pydantic model, loaded via
  ``AppConfig.from_env()``.
* ``BrokerSettings`` / ``SettingsLoaderBase`` = broker-specific configuration
  (client_id, access_token, PIN, TOTP, timeouts, sandbox endpoints, resilience).
  Loaded per-broker via ``DhanSettingsLoader``, ``UpstoxSettingsLoader`` etc.
  These handle broker-prefixed env vars (``DHAN_*``, ``UPSTOX_*``),
  ``.env`` file discovery, and ``SecretsManager`` integration.

The two systems serve different consumers and different env-var namespaces,
so the dual-config architecture is intentional.  Do NOT merge them.

Phase 3 (Configuration Centralization) — both :class:`DhanConnectionSettings`
and :class:`UpstoxConnectionSettings` inherit from :class:`BrokerSettings`,
and their loaders inherit from :class:`SettingsLoaderBase`, eliminating
duplicated field definitions and env-var parsing logic.

Usage::

    from infrastructure.config.settings import BrokerSettings, SettingsLoaderBase

    class DhanConnectionSettings(BrokerSettings):
        base_url: str = "https://api.dhan.co/v2"
        ...

    class DhanSettingsLoader(SettingsLoaderBase):
        PREFIX = "DHAN"
        ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrokerSettings:
    """Common broker connection settings — shared by all broker adapters.

    Every broker at minimum needs a *client_id* and an *access_token*.
    The remaining fields carry sensible defaults that match the majority
    of deployment scenarios.
    """

    client_id: str
    access_token: str = ""
    http_timeout: float = 15.0
    enable_retry: bool = True
    pool_connections: int = 50
    pool_maxsize: int = 100


class SettingsLoaderBase:
    """Base class for broker-specific settings loaders.

    Provides:
    * Default env file discovery (``.env.local`` → ``.env``).
    * ``load_env_file()`` integration via :func:`infrastructure.config.env_loader.load_env_file`.
    * Parse helpers for int, float, bool.
    * Simple ``_get()`` lookup.

    Subclasses set :attr:`PREFIX` and call :meth:`from_env` or
    :meth:`from_dict`.

    This is intentionally separate from :class:`config.schema.AppConfig`.
    See module docstring for rationale.
    """

    PREFIX: str = ""
    """Environment variable prefix (e.g. ``\"DHAN\"``, ``\"UPSTOX\"``)."""

    DEFAULT_ENV_PATHS: tuple[Path, ...] = (Path(".env.local"), Path(".env"))
    """Env files checked in order when no explicit path is given."""

    # ── Environment loading ──────────────────────────────────────────

    @classmethod
    def _load_env_file(cls, path: Path) -> None:
        """Load *path* via :func:`infrastructure.config.env_loader.load_env_file`."""
        from infrastructure.config.env_loader import load_env_file

        load_env_file(path)

    @classmethod
    def _load_default_env(cls, env_path: Path | None) -> None:
        """Load the env file at *env_path*, or try each default path."""
        if env_path is not None:
            cls._load_env_file(env_path)
            return
        for candidate in cls.DEFAULT_ENV_PATHS:
            if candidate.exists():
                cls._load_env_file(candidate)
                break

    # ── Env var accessors ────────────────────────────────────────────

    @classmethod
    def _get(cls, prefix: str, name: str, default: str = "") -> str:
        """Look up ``{PREFIX}_{NAME}`` in the current process environment.

        Subclasses may override to support multiple candidate keys
        (e.g. legacy aliases, dotted names).
        """
        return os.environ.get(f"{prefix.upper()}_{name.upper()}", "") or default

    @classmethod
    def _get_int(cls, prefix: str, name: str, default: int) -> int:
        raw = cls._get(prefix, name)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @classmethod
    def _get_float(cls, prefix: str, name: str, default: float) -> float:
        raw = cls._get(prefix, name)
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    @classmethod
    def _get_bool(cls, prefix: str, name: str, default: bool) -> bool:
        raw = cls._get(prefix, name).lower()
        if not raw:
            return default
        return raw in ("1", "true", "yes", "y", "on")

    # ── Value parsers ────────────────────────────────────────────────

    @staticmethod
    def _parse_int(value: str, default: int) -> int:
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_float(value: str, default: float) -> float:
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_bool(value: str, default: bool) -> bool:
        if not value:
            return default
        return value.lower() in ("1", "true", "yes", "y", "on")
