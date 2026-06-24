"""Tests for config schema — verifies all env vars have typed defaults."""

from __future__ import annotations

import os
from typing import ClassVar
from unittest.mock import patch

import pytest

from config.schema import (
    ApiConfig,
    DhanConfig,
    TradingConfig,
    UpstoxConfig,
    load_api_config,
    load_dhan_config,
    load_trading_config,
    load_upstox_config,
)


class TestDhanConfig:
    def test_default_values(self):
        config = DhanConfig()
        assert config.client_id == ""
        assert config.access_token == ""
        assert config.environment == "LIVE"
        assert config.allow_live_orders is False
        assert config.refresh_buffer_minutes == 10

    def test_load_from_env(self):
        env = {
            "DHAN_CLIENT_ID": "test_client",
            "DHAN_ACCESS_TOKEN": "test_token",
            "DHAN_ENVIRONMENT": "SANDBOX",
            "DHAN_PIN": "1234",
            "DHAN_TOTP_SECRET": "ABCDEF",
            "DHAN_ALLOW_LIVE_ORDERS": "1",
            "DHAN_REFRESH_BUFFER_MINUTES": "5",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_dhan_config()
            assert config.client_id == "test_client"
            assert config.access_token == "test_token"
            assert config.environment == "SANDBOX"
            assert config.pin == "1234"
            assert config.totp_secret == "ABCDEF"
            assert config.allow_live_orders is True
            assert config.refresh_buffer_minutes == 5

    def test_frozen(self):
        config = DhanConfig()
        with pytest.raises(AttributeError):
            config.client_id = "new"


class TestUpstoxConfig:
    def test_default_values(self):
        config = UpstoxConfig()
        assert config.client_id == ""
        assert config.environment == "LIVE"
        assert config.auth_mode == "STATIC"
        assert config.analytics_only is False
        assert config.allow_live_orders is False
        assert config.totp_refresh_hour == 8

    def test_load_from_env(self):
        env = {
            "UPSTOX_CLIENT_ID": "upstox_client",
            "UPSTOX_ACCESS_TOKEN": "upstox_token",
            "UPSTOX_ENVIRONMENT": "SANDBOX",
            "UPSTOX_ANALYTICS_ONLY": "1",
            "UPSTOX_ALLOW_LIVE_ORDERS": "1",
            "UPSTOX_TOTP_REFRESH_HOUR": "6",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_upstox_config()
            assert config.client_id == "upstox_client"
            assert config.access_token == "upstox_token"
            assert config.environment == "SANDBOX"
            assert config.analytics_only is True
            assert config.allow_live_orders is True
            assert config.totp_refresh_hour == 6


class TestApiConfig:
    def test_default_values(self):
        config = ApiConfig()
        assert config.auth_mode == "none"
        assert config.api_key == ""

    def test_load_from_env(self):
        env = {"AUTH_MODE": "api_key", "API_KEY": "secret_key"}
        with patch.dict(os.environ, env, clear=False):
            config = load_api_config()
            assert config.auth_mode == "api_key"
            assert config.api_key == "secret_key"


class TestTradingConfig:
    def test_default_values(self):
        config = TradingConfig()
        assert config.orchestrator_dry_run is True
        assert config.orchestrator_min_confidence == 0.7
        assert config.enable_intelligent_gateway is False
        assert config.skip_parity_gate is False

    def test_load_from_env(self):
        env = {
            "ORCHESTRATOR_DRY_RUN": "0",
            "ORCHESTRATOR_MIN_CONFIDENCE": "0.9",
            "ENABLE_INTELLIGENT_GATEWAY": "1",
            "SKIP_PARITY_GATE": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_trading_config()
            assert config.orchestrator_dry_run is False
            assert config.orchestrator_min_confidence == 0.9
            assert config.enable_intelligent_gateway is True
            assert config.skip_parity_gate is True


class TestConfigAllEnvVars:
    """Verify every expected env var is handled by the config loaders."""

    EXPECTED_DHAN_VARS: ClassVar[list[str]] = [
        "DHAN_CLIENT_ID",
        "DHAN_ACCESS_TOKEN",
        "DHAN_ENVIRONMENT",
        "DHAN_REST_BASE_URL",
        "DHAN_PIN",
        "DHAN_TOTP_SECRET",
        "DHAN_TOKEN_STATE_FILE",
        "DHAN_REFRESH_BUFFER_MINUTES",
        "DHAN_ALLOW_LIVE_ORDERS",
        "DHAN_SANDBOX_CLIENT_ID",
        "DHAN_SANDBOX_ACCESS_TOKEN",
    ]

    EXPECTED_UPSTOX_VARS: ClassVar[list[str]] = [
        "UPSTOX_CLIENT_ID",
        "UPSTOX_CLIENT_SECRET",
        "UPSTOX_ACCESS_TOKEN",
        "UPSTOX_ANALYTICS_TOKEN",
        "UPSTOX_ENVIRONMENT",
        "UPSTOX_AUTH_MODE",
        "UPSTOX_REDIRECT_URI",
        "UPSTOX_TOKEN_STATE_FILE",
        "UPSTOX_ANALYTICS_ONLY",
        "UPSTOX_ALLOW_LIVE_ORDERS",
        "UPSTOX_MOBILE",
        "UPSTOX_PIN",
        "UPSTOX_TOTP_SECRET",
        "UPSTOX_TOTP_REFRESH_HOUR",
        "UPSTOX_TOTP_REFRESH_MINUTE",
    ]

    def test_all_dhan_vars_handled(self):
        for var in self.EXPECTED_DHAN_VARS:
            with patch.dict(os.environ, {var: "test_value"}, clear=False):
                config = load_dhan_config()
                assert config is not None, f"Failed to load config with {var} set"

    def test_all_upstox_vars_handled(self):
        for var in self.EXPECTED_UPSTOX_VARS:
            with patch.dict(os.environ, {var: "test_value"}, clear=False):
                config = load_upstox_config()
                assert config is not None, f"Failed to load config with {var} set"
