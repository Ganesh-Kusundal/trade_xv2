"""Environment profile — one dataclass + env table."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EnvironmentProfile:
    """Environment-specific configuration."""

    name: str = "base"
    log_level: str = "INFO"
    debug_enabled: bool = False
    mock_brokers_allowed: bool = False
    strict_validation: bool = True
    allow_live_orders_by_default: bool = False
    encryption_required: bool = False
    api_auth_required: bool = False
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 0
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    observability_enabled: bool = False
    metrics_endpoint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROFILE_TABLE: dict[str, dict[str, Any]] = {
    "base": {},
    "dev": {
        "name": "dev",
        "log_level": "DEBUG",
        "debug_enabled": True,
        "mock_brokers_allowed": True,
        "strict_validation": False,
        "cors_origins": [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
    },
    "staging": {
        "name": "staging",
        "log_level": "INFO",
        "debug_enabled": True,
        "encryption_required": True,
        "api_auth_required": True,
        "rate_limit_enabled": True,
        "rate_limit_per_minute": 120,
        "cors_origins": [
            "https://staging.tradexv2.com",
            "http://localhost:5173",
        ],
        "observability_enabled": True,
        "metrics_endpoint": "http://localhost:9090/metrics",
    },
    "prod": {
        "name": "prod",
        "log_level": "WARNING",
        "encryption_required": True,
        "api_auth_required": True,
        "rate_limit_enabled": True,
        "rate_limit_per_minute": 60,
        "cors_origins": ["https://app.tradexv2.com"],
        "observability_enabled": True,
    },
}


def _make_profile_type(env_name: str, class_name: str) -> type[EnvironmentProfile]:
    spec = _PROFILE_TABLE[env_name]

    class _Profile(EnvironmentProfile):
        def __init__(self) -> None:
            super().__init__(**spec)

    _Profile.__name__ = class_name
    _Profile.__qualname__ = class_name
    return _Profile


BaseProfile = _make_profile_type("base", "BaseProfile")
DevProfile = _make_profile_type("dev", "DevProfile")
StagingProfile = _make_profile_type("staging", "StagingProfile")
ProdProfile = _make_profile_type("prod", "ProdProfile")
