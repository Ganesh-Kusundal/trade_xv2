"""Tests for api.config — APIConfig defaults and conversion."""

from __future__ import annotations

from api.config import APIConfig


class TestAPIConfigDefaults:
    def test_default_host(self):
        cfg = APIConfig()
        assert cfg.host == "127.0.0.1"

    def test_default_port(self):
        cfg = APIConfig()
        assert cfg.port == 8080

    def test_default_auth_mode_is_api_key(self):
        """ENG-004: API is secure by default."""
        cfg = APIConfig()
        assert cfg.auth_mode == "api_key"

    def test_default_rate_limit(self):
        cfg = APIConfig()
        assert cfg.rate_limit_per_minute == 100

    def test_default_cors_origins(self):
        cfg = APIConfig()
        assert "http://localhost:5173" in cfg.cors_origins

    def test_docs_url(self):
        cfg = APIConfig()
        assert cfg.docs_url == "/docs"

    def test_redoc_url(self):
        cfg = APIConfig()
        assert cfg.redoc_url == "/redoc"

    def test_openapi_url(self):
        cfg = APIConfig()
        assert cfg.openapi_url == "/openapi.json"


class TestFromAppConfig:
    def test_maps_fields(self):
        from config.schema import AppConfig

        app_cfg = AppConfig(
            api_host="0.0.0.0",
            api_port=9000,
            cors_origins=["https://example.com"],
            rate_limit_max_requests=200,
        )
        cfg = APIConfig.from_app_config(app_cfg)
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9000
        assert cfg.cors_origins == ["https://example.com"]
        assert cfg.rate_limit_per_minute == 200
