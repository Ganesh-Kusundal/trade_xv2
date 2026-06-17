from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from brokers.common.env_loader import load_env_file

UPSTOX_PREFIX = "UPSTOX"

VALID_ENVIRONMENTS = ("LIVE", "SANDBOX")
VALID_AUTH_MODES = ("STATIC", "OAUTH", "INTERACTIVE", "EXTENDED", "WEBHOOK")


@dataclass(frozen=True)
class UpstoxConnectionSettings:
    """Resolved Upstox connection settings.

    Mirrors Trade_J ``UpstoxConnectionSettings`` (Java record).
    """

    client_id: str
    client_secret: str = ""
    redirect_uri: str = "http://localhost:18080"
    auth_mode: str = "STATIC"
    environment: str = "LIVE"
    rest_base_url: str = ""
    access_token: str = ""
    refresh_token: str = ""
    extended_token: str = ""
    analytics_token: str = ""
    analytics_only: bool = False
    token_state_file: Path | None = None
    instrument_cache: Path = field(default_factory=lambda: Path(".cache/upstox/complete.json.gz"))
    refresh_buffer_minutes: int = 30
    redirect_port: int = 18080
    algo_name: str = ""
    static_ip: str = ""
    allow_live_orders: bool = True
    pool_connections: int = 50
    pool_maxsize: int = 100
    market_protection_default: int = -1
    slice_default: bool = False
    ws_plus_plan: bool = False
    ws_max_connections: int = 2
    ws_auto_reconnect: bool = True
    ws_reconnect_interval_s: int = 10
    ws_reconnect_max_retries: int = 5

    @property
    def is_sandbox(self) -> bool:
        return self.environment.upper() == "SANDBOX"

    @property
    def is_live(self) -> bool:
        return self.environment.upper() == "LIVE"

    @property
    def is_static(self) -> bool:
        return self.auth_mode.upper() == "STATIC"

    @property
    def is_oauth(self) -> bool:
        return self.auth_mode.upper() == "OAUTH"

    @property
    def is_interactive(self) -> bool:
        return self.auth_mode.upper() == "INTERACTIVE"

    @property
    def is_extended(self) -> bool:
        return self.auth_mode.upper() == "EXTENDED"

    @property
    def is_webhook(self) -> bool:
        return self.auth_mode.upper() == "WEBHOOK"

    @property
    def has_access_token(self) -> bool:
        return bool(self.access_token)

    @property
    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)

    @property
    def has_extended_token(self) -> bool:
        return bool(self.extended_token)

    @property
    def has_refresh(self) -> bool:
        return bool(self.refresh_token)

    @property
    def rest_base_override(self) -> str:
        return self.rest_base_url.rstrip("/") if self.rest_base_url else ""

    @property
    def instrument_cache_path(self) -> Path:
        """Alias for :attr:`instrument_cache` for older call sites."""
        return self.instrument_cache

    @property
    def base_v2(self) -> str:
        if self.rest_base_url:
            return self.rest_base_url.rstrip("/")
        if self.is_sandbox:
            return "https://sandbox-api.upstox.com"
        return "https://api.upstox.com"

    @property
    def base_hft(self) -> str:
        if self.is_sandbox:
            return "https://sandbox-api-hft.upstox.com"
        return "https://api-hft.upstox.com"


class UpstoxSettingsLoader:
    """Load :class:`UpstoxConnectionSettings` from env / dotenv / .properties.

    Mirrors Trade_J ``UpstoxConnectionSettings`` env conventions.
    """

    PREFIX = UPSTOX_PREFIX
    DEFAULT_ENV_PATHS = (Path(".env.local"), Path(".env"))

    @classmethod
    def from_env(
        cls,
        *,
        env_path: Path | None = None,
        prefix: str = PREFIX,
    ) -> UpstoxConnectionSettings:
        if env_path:
            load_env_file(env_path)
        else:
            for candidate in cls.DEFAULT_ENV_PATHS:
                if candidate.exists():
                    load_env_file(candidate)
                    break

        environment = cls._get(prefix, "ENVIRONMENT", default="LIVE").upper()
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"UPSTOX_ENVIRONMENT must be one of {VALID_ENVIRONMENTS}, got {environment!r}"
            )
        is_sandbox = environment == "SANDBOX"
        client_id = (
            cls._get(prefix, "SANDBOX_CLIENT_ID")
            or cls._get(prefix, "CLIENT_ID")
            or cls._get(prefix, "client.clientId")
        )
        if not client_id:
            raise ValueError("UPSTOX_CLIENT_ID is required")

        if is_sandbox and cls._get(prefix, "SANDBOX_REST_BASE_URL"):
            rest_base_url = cls._get(prefix, "SANDBOX_REST_BASE_URL")
        else:
            rest_base_url = cls._get(prefix, "REST_BASE_URL") or ""

        auth_mode = cls._get(prefix, "AUTH_MODE", default="STATIC").upper()
        if auth_mode not in VALID_AUTH_MODES:
            raise ValueError(
                f"UPSTOX_AUTH_MODE must be one of {VALID_AUTH_MODES}, got {auth_mode!r}"
            )

        client_secret = (
            cls._get(prefix, "SANDBOX_CLIENT_SECRET") or cls._get(prefix, "CLIENT_SECRET")
        ) or ""
        access_token = (
            cls._get(prefix, "SANDBOX_ACCESS_TOKEN") or cls._get(prefix, "ACCESS_TOKEN")
        ) or ""
        refresh_token = cls._get(prefix, "REFRESH_TOKEN") or ""
        extended_token = cls._get(prefix, "EXTENDED_TOKEN") or ""
        analytics_token = cls._get(prefix, "ANALYTICS_TOKEN") or ""
        algo_name = cls._get(prefix, "ALGO_NAME") or ""
        static_ip = cls._get(prefix, "STATIC_IP") or ""
        analytics_only = cls._get_bool(prefix, "ANALYTICS_ONLY", default=False)
        allow_live_orders = cls._get_bool(prefix, "ALLOW_LIVE_ORDERS", default=True)
        ws_plus_plan = cls._get_bool(prefix, "WS_PLUS_PLAN", default=False)
        slice_default = cls._get_bool(prefix, "SLICE_DEFAULT", default=False)
        market_protection_default = cls._get_int(prefix, "MARKET_PROTECTION_DEFAULT", default=-1)
        redirect_port = cls._get_int(prefix, "REDIRECT_PORT", default=18080)
        refresh_buffer_minutes = cls._get_int(prefix, "REFRESH_BUFFER_MINUTES", default=30)

        token_state_file_path = cls._get(prefix, "TOKEN_STATE_FILE")
        token_state_file = Path(token_state_file_path) if token_state_file_path else None
        instrument_cache_str = cls._get(
            prefix, "INSTRUMENT_CACHE", default=".cache/upstox/complete.json.gz"
        )
        instrument_cache = Path(instrument_cache_str)

        return UpstoxConnectionSettings(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=cls._get(
                prefix, "REDIRECT_URI", default=f"http://localhost:{redirect_port}"
            ),
            auth_mode=auth_mode,
            environment=environment,
            rest_base_url=rest_base_url,
            access_token=access_token,
            refresh_token=refresh_token,
            extended_token=extended_token,
            analytics_token=analytics_token,
            analytics_only=analytics_only,
            token_state_file=token_state_file,
            instrument_cache=instrument_cache,
            refresh_buffer_minutes=refresh_buffer_minutes,
            redirect_port=redirect_port,
            algo_name=algo_name,
            static_ip=static_ip,
            allow_live_orders=allow_live_orders,
            market_protection_default=market_protection_default,
            slice_default=slice_default,
            ws_plus_plan=ws_plus_plan,
        )

    @classmethod
    def from_properties(cls, path: Path, *, prefix: str = "upstox") -> UpstoxConnectionSettings:
        """Load from a Trade_J-style ``upstox-live.properties`` file."""
        values = cls._read_properties(path)
        environment = (values.get("upstox.environment") or "LIVE").upper()
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"upstox.environment must be one of {VALID_ENVIRONMENTS}, got {environment!r}"
            )
        client_id = values.get(f"{prefix}.clientId")
        if not client_id:
            raise ValueError(f"{path} must contain {prefix}.clientId")

        auth_mode = (values.get(f"{prefix}.authMode") or "STATIC").upper()
        if auth_mode not in VALID_AUTH_MODES:
            raise ValueError(
                f"{prefix}.authMode must be one of {VALID_AUTH_MODES}, got {auth_mode!r}"
            )

        return UpstoxConnectionSettings(
            client_id=client_id,
            client_secret=values.get(f"{prefix}.clientSecret", ""),
            redirect_uri=values.get(f"{prefix}.redirectUri", "http://localhost:18080"),
            access_token=values.get(f"{prefix}.accessToken", ""),
            refresh_token=values.get(f"{prefix}.refreshToken", ""),
            extended_token=values.get(f"{prefix}.extendedToken", ""),
            analytics_token=values.get(f"{prefix}.analyticsToken", ""),
            analytics_only=cls._parse_bool(values.get(f"{prefix}.analyticsOnly"), False),
            auth_mode=auth_mode,
            environment=environment,
            rest_base_url=values.get(f"{prefix}.restBaseUrl", ""),
            token_state_file=cls._path_from_env(values.get(f"{prefix}.tokenStateFile")),
            instrument_cache=cls._path_from_env(
                values.get(f"{prefix}.instrumentCache"), Path(".cache/upstox/complete.json.gz")
            ),
            refresh_buffer_minutes=cls._parse_int(values.get(f"{prefix}.refreshBufferMinutes"), 30),
            redirect_port=cls._parse_int(values.get(f"{prefix}.redirectPort"), 18080),
            algo_name=values.get(f"{prefix}.algoName", ""),
            static_ip=values.get(f"{prefix}.staticIp", ""),
            allow_live_orders=cls._parse_bool(values.get(f"{prefix}.allowLiveOrders"), True),
            ws_plus_plan=cls._parse_bool(values.get(f"{prefix}.wsPlusPlan"), False),
            market_protection_default=cls._parse_int(
                values.get(f"{prefix}.marketProtectionDefault"), -1
            ),
            slice_default=cls._parse_bool(values.get(f"{prefix}.sliceDefault"), False),
        )

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
        candidates = [
            f"{prefix.upper()}_{normalized}",
            f"{prefix.upper()}.{name}",
            f"{prefix.lower()}.{name}",
        ]
        # Backward-compat fallbacks for legacy env var names.
        name_lower = name.lower()
        if name_lower == "client_id":
            candidates.insert(0, f"{prefix.upper()}_API_KEY")
        elif name_lower == "client_secret":
            candidates.insert(0, f"{prefix.upper()}_API_SECRET")
        elif name_lower == "access_token":
            candidates.insert(0, f"{prefix.upper()}_API_ACCESS_TOKEN")
        for candidate in candidates:
            value = os.environ.get(candidate)
            if value:
                return value
        return default

    @staticmethod
    def _get_int(prefix: str, name: str, default: int) -> int:
        raw = UpstoxSettingsLoader._get(prefix, name)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @staticmethod
    def _get_bool(prefix: str, name: str, default: bool) -> bool:
        raw = UpstoxSettingsLoader._get(prefix, name).lower()
        if not raw:
            return default
        return raw in ("1", "true", "yes", "y", "on")

    @staticmethod
    def _parse_int(value: str | None, default: int) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_bool(value: str | None, default: bool) -> bool:
        if value is None or value == "":
            return default
        return str(value).lower() in ("1", "true", "yes", "y", "on")

    @staticmethod
    def _path_from_env(value: str | None, default: Path | None = None) -> Path | None:
        if not value:
            return default
        return Path(value)
