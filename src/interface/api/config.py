"""Backward-compat shim — canonical config is config.schema.AppConfig."""

from __future__ import annotations

from config.schema import AppConfig


class APIConfig(AppConfig):
    """Thin shim that maps legacy APIConfig field names to AppConfig fields.

    Canonical configuration lives in ``config.schema.AppConfig``.  This class
    exists solely so that existing ``from interface.api.config import APIConfig``
    imports and constructor call-sites (``APIConfig(host=..., port=...)``) keep
    working without changes.
    """

    def __init__(self, **data: object) -> None:
        # Map legacy ``host`` / ``port`` → AppConfig's ``api_host`` / ``api_port``
        if "host" in data:
            data.setdefault("api_host", data.pop("host"))
        if "port" in data:
            data.setdefault("api_port", data.pop("port"))
        # Map legacy ``rate_limit_per_minute`` → AppConfig's ``rate_limit_max_requests``
        if "rate_limit_per_minute" in data:
            data.setdefault("rate_limit_max_requests", data.pop("rate_limit_per_minute"))
        super().__init__(**data)

    # ── Legacy attribute aliases (read-side) ────────────────

    @property
    def host(self) -> str:  # type: ignore[override]
        return self.api_host

    @property
    def port(self) -> int:  # type: ignore[override]
        return self.api_port

    @property
    def rate_limit_per_minute(self) -> int:  # type: ignore[override]
        return self.rate_limit_max_requests

    # ── Documentation URL properties ────────────────────────

    @property
    def docs_url(self) -> str:
        """URL for Swagger UI documentation."""
        return "/docs"

    @property
    def redoc_url(self) -> str:
        """URL for ReDoc documentation."""
        return "/redoc"

    @property
    def openapi_url(self) -> str:
        """URL for OpenAPI JSON schema."""
        return "/openapi.json"

    # ── Conversion ──────────────────────────────────────────

    @classmethod
    def from_app_config(cls, app_cfg: AppConfig) -> APIConfig:
        """Create an APIConfig from the central AppConfig."""
        return cls(
            api_host=app_cfg.api_host,
            api_port=app_cfg.api_port,
            cors_origins=app_cfg.cors_origins,
            rate_limit_max_requests=app_cfg.rate_limit_max_requests,
            auth_mode=getattr(app_cfg, "auth_mode", "none"),
            api_key=getattr(app_cfg, "api_key", ""),
        )


__all__ = ["APIConfig"]
