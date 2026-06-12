"""Dhan connection settings — Trade_J ``dhan-local.properties`` compatible.

:class:`DhanConnectionSettings` is the single source of truth for all
required and optional connection parameters, and
:class:`DhanSettingsLoader` reads it from ``.env``, ``.env.local``, or a
Java-style ``.properties`` file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DHAN_PREFIX = "DHAN"


@dataclass(frozen=True)
class DhanConnectionSettings:
    """Resolved Dhan connection settings.

    All secret paths are optional; the loader supports inline values
    (``DHAN_PIN`` / ``DHAN_TOTP_SECRET``) in addition to file-based
    secrets (``DHAN_PIN_FILE`` / ``DHAN_TOTP_SECRET_FILE``).
    """

    client_id: str
    access_token: str = ""
    auth_mode: str = "STATIC"
    environment: str = "LIVE"
    rest_base_url: str = ""
    pin: str | None = None
    totp_secret: str | None = None
    pin_file: Path | None = None
    totp_secret_file: Path | None = None
    token_state_file: Path | None = None
    refresh_buffer_minutes: int = 10
    instrument_cache_dir: Path | None = None
    instrument_strict_resolution: bool = True

    @property
    def is_totp_generated(self) -> bool:
        return self.auth_mode.upper() == "TOTP_GENERATED"

    @property
    def is_web_renewable(self) -> bool:
        return self.auth_mode.upper() == "WEB_RENEWABLE"

    @property
    def is_static(self) -> bool:
        return self.auth_mode.upper() == "STATIC"

    @property
    def is_sandbox(self) -> bool:
        return self.environment.upper() == "SANDBOX"


class DhanSettingsLoader:
    """Load :class:`DhanConnectionSettings` from environment / dotenv / ``.properties``.

    Environment variable conventions (prefix ``DHAN``):

    ===================================  =========================
    Variable                             Notes
    ===================================  =========================
    ``DHAN_CLIENT_ID``                   Required.
    ``DHAN_ACCESS_TOKEN``                STATIC mode token.
    ``DHAN_AUTH_MODE``                   ``STATIC`` (default),
                                         ``TOTP_GENERATED``,
                                         ``WEB_RENEWABLE``.
    ``DHAN_ENVIRONMENT``                 ``LIVE`` (default) /
                                         ``SANDBOX``.
    ``DHAN_REST_BASE_URL``               Override the REST base URL.
    ``DHAN_PIN`` / ``DHAN_TOTP_SECRET``  Inline secrets (alternative
                                         to the ``_FILE`` variants).
    ``DHAN_PIN_FILE``                    Path to a file containing PIN.
    ``DHAN_TOTP_SECRET_FILE``            Path to a file containing TOTP
                                         secret (Base32).
    ``DHAN_TOKEN_STATE_FILE``            File path for persisting token
                                         state across restarts.
    ``DHAN_REFRESH_BUFFER_MINUTES``      Minutes before expiry to
                                         proactively refresh (default 10).
    ===================================  =========================

    Trade_J properties keys are also supported when using
    :meth:`from_properties`:

    ``dhan.clientId`` ``dhan.accessToken`` ``dhan.authMode``
    ``dhan.environment`` ``dhan.restBaseUrl``
    """

    PREFIX = DHAN_PREFIX
    DEFAULT_ENV_PATHS = (Path(".env.local"), Path(".env"))

    @classmethod
    def from_env(
        cls,
        *,
        env_path: Path | None = None,
        prefix: str = PREFIX,
    ) -> DhanConnectionSettings:
        # Load dotenv file if given, otherwise probe the two defaults.
        if env_path:
            cls._load_dotenv(env_path)
        else:
            for candidate in cls.DEFAULT_ENV_PATHS:
                if candidate.exists():
                    cls._load_dotenv(candidate)
                    break

        environment = cls._get(prefix, "ENVIRONMENT", default="LIVE")
        use_sandbox = environment.upper() == "SANDBOX"
        client_id = (
            cls._get(prefix, "SANDBOX_CLIENT_ID") if use_sandbox else cls._get(prefix, "CLIENT_ID")
        ) or cls._get(prefix, "client.clientId")

        if not client_id:
            raise ValueError("DHAN_CLIENT_ID is required")

        access_token = (
            cls._get(prefix, "SANDBOX_ACCESS_TOKEN")
            if use_sandbox
            else cls._get(prefix, "ACCESS_TOKEN")
        ) or ""
        rest_base_url = (
            cls._get(prefix, "SANDBOX_REST_BASE_URL")
            if use_sandbox
            else cls._get(prefix, "REST_BASE_URL")
        ) or ""
        refresh = cls._get_int(prefix, "REFRESH_BUFFER_MINUTES", default=10)

        instrument_cache_dir = cls._path_from_env(cls._get(prefix, "INSTRUMENT_CACHE_DIR"))
        instrument_strict = cls._get_bool(prefix, "INSTRUMENT_STRICT_RESOLUTION", default=True)

        return DhanConnectionSettings(
            client_id=client_id,
            access_token=access_token,
            auth_mode=cls._get(prefix, "AUTH_MODE", default="STATIC"),
            environment=environment,
            rest_base_url=rest_base_url,
            pin=cls._get(prefix, "PIN") or None,
            totp_secret=cls._get(prefix, "TOTP_SECRET") or None,
            pin_file=cls._path_from_env(cls._get(prefix, "PIN_FILE")),
            totp_secret_file=cls._path_from_env(cls._get(prefix, "TOTP_SECRET_FILE")),
            token_state_file=cls._path_from_env(cls._get(prefix, "TOKEN_STATE_FILE")),
            refresh_buffer_minutes=refresh,
            instrument_cache_dir=instrument_cache_dir,
            instrument_strict_resolution=instrument_strict,
        )

    @classmethod
    def from_properties(cls, path: Path, *, prefix: str = "dhan") -> DhanConnectionSettings:
        """Load from a Trade_J-style ``dhan-local.properties`` file."""
        values = cls._read_properties(path)
        client_id = values.get(f"{prefix}.clientId") or values.get("clientId")
        if not client_id:
            raise ValueError(f"{path} must contain {prefix}.clientId")

        refresh = cls._parse_int(values.get(f"{prefix}.refreshBufferMinutes"), default=10)
        instrument_cache_dir = cls._path_from_env(values.get(f"{prefix}.instrumentCacheDir"))
        instrument_strict_raw = (
            values.get(f"{prefix}.instrumentStrictResolution", "").strip().lower()
        )
        instrument_strict = (
            True
            if not instrument_strict_raw
            else instrument_strict_raw in {"1", "true", "yes", "on"}
        )
        return DhanConnectionSettings(
            client_id=client_id,
            access_token=values.get(f"{prefix}.accessToken", ""),
            auth_mode=values.get(f"{prefix}.authMode", "STATIC"),
            environment=values.get(f"{prefix}.environment", "LIVE"),
            rest_base_url=values.get(f"{prefix}.restBaseUrl", ""),
            pin=values.get(f"{prefix}.pin"),
            totp_secret=values.get(f"{prefix}.totpSecret"),
            pin_file=cls._path_from_env(values.get(f"{prefix}.pinFile")),
            totp_secret_file=cls._path_from_env(values.get(f"{prefix}.totpSecretFile")),
            token_state_file=cls._path_from_env(values.get(f"{prefix}.tokenStateFile")),
            refresh_buffer_minutes=refresh,
            instrument_cache_dir=instrument_cache_dir,
            instrument_strict_resolution=instrument_strict,
        )

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _load_dotenv(path: Path) -> None:
        if not path.exists():
            return
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
            normalized = key.replace(".", "_").upper()
            os.environ.setdefault(normalized, value)

    @staticmethod
    def _read_properties(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        if not path.exists():
            return values
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _get(prefix: str, name: str, default: str = "") -> str:
        upper_name = name.upper()
        normalized = upper_name.replace(".", "_")
        for candidate in (
            f"{prefix.upper()}_{normalized}",
            f"{prefix.upper()}.{name}",
        ):
            value = os.environ.get(candidate)
            if value:
                return value
        return default

    @staticmethod
    def _get_int(prefix: str, name: str, default: int) -> int:
        return DhanSettingsLoader._parse_int(DhanSettingsLoader._get(prefix, name), default)

    @staticmethod
    def _parse_int(value: str | None, default: int) -> int:
        if value is None or value == "":
            return default
        return int(value)

    @staticmethod
    def _get_bool(prefix: str, name: str, default: bool) -> bool:
        raw = DhanSettingsLoader._get(prefix, name, default="").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _path_from_env(value: str | None) -> Path | None:
        if not value:
            return None
        return Path(value)
