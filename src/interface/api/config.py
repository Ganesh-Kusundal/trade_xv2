"""API configuration — CORS, rate limits, and server settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.schema import AppConfig


@dataclass
class APIConfig:
    """Configuration for the TradeXV2 API server.

    Parameters
    ----------
    host:
        Bind address. Default "127.0.0.1" (loopback only).
    port:
        TCP port. Default 8080.
    cors_origins:
        Allowed CORS origins. Default includes Vite dev server.
    cors_allow_credentials:
        Whether to allow credentials in CORS requests.
    cors_allow_methods:
        Allowed HTTP methods for CORS.
    cors_allow_headers:
        Allowed HTTP headers for CORS.
    max_page_size:
        Maximum number of items per page for paginated responses.
    default_page_size:
        Default number of items per page.
    rate_limit_per_minute:
        Maximum requests per minute per client (0 = disabled).
    api_prefix:
        URL prefix for all API routes (e.g., "/api/v1").
    """

    host: str = "127.0.0.1"
    port: int = 8080
    cors_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative dev port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    cors_allow_headers: list[str] = field(
        default_factory=lambda: ["Authorization", "Content-Type", "X-Correlation-ID"]
    )
    max_page_size: int = 1000
    default_page_size: int = 100
    rate_limit_per_minute: int = 100  # 100 req/min per IP; 0 = disabled
    api_prefix: str = "/api/v1"
    # ENG-004: secure by default. Local/dev may set auth_mode="none" explicitly
    # (or AUTH_MODE=none via env mapped at composition root).
    auth_mode: str = "api_key"  # "none" or "api_key"
    api_key: str = ""  # API key (generated if empty and auth_mode=api_key)

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

    @classmethod
    def from_app_config(cls, app_cfg: AppConfig) -> APIConfig:
        """Create an APIConfig from the central AppConfig.

        Maps central config fields to API-specific fields. Explicit kwargs
        passed to the constructor override values derived from AppConfig.
        """
        return cls(
            host=app_cfg.api_host,
            port=app_cfg.api_port,
            cors_origins=app_cfg.cors_origins,
            rate_limit_per_minute=app_cfg.rate_limit_max_requests,
        )
