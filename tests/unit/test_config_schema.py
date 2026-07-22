"""Tests for config schema — verifies all env vars have typed defaults."""

from __future__ import annotations

import os
from unittest.mock import patch

from config.schema import (
    ApiConfig,
    TradingConfig,
    load_api_config,
    load_trading_config,
)


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
        assert config.orchestrator_dry_run is False
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
