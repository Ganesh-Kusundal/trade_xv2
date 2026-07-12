"""Config validation integration tests.

Verifies that config validation (from Phase 6, Task 6.6) works correctly
in production flow.

These tests use REAL config objects — no mocking of validation logic.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brokers.dhan.config.settings import DhanSettingsLoader

# ── Fixture to isolate tests from workspace .env.local ─────────────────

@pytest.fixture(autouse=True)
def _isolate_dhan_env():
    """Save and restore DHAN_* env vars to prevent workspace .env.local leakage."""
    # Save existing DHAN_* env vars
    saved = {k: v for k, v in os.environ.items() if k.startswith("DHAN_")}

    # Clear all DHAN_* vars
    for k in list(os.environ.keys()):
        if k.startswith("DHAN_"):
            del os.environ[k]

    yield

    # Restore original DHAN_* vars
    for k, v in saved.items():
        os.environ[k] = v


# ── Test 1: Valid config passes validation ──────────────────────────────

class TestValidConfig:
    """Verify valid config passes validation."""

    def test_validate_config_passes_with_valid_config(self, tmp_path: Path) -> None:
        """A complete, valid .env file must produce valid settings."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=test_client_123\n"
            "DHAN_ACCESS_TOKEN=test_token_abc\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRETKEY\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)

        assert settings.client_id == "test_client_123"
        assert settings.access_token == "test_token_abc"
        assert settings.http_timeout == 15.0  # default
        assert settings.enable_retry is True  # default
        assert settings.pool_connections == 50  # default
        assert settings.pool_maxsize == 100  # default

    def test_validate_config_with_sandbox_env(self, tmp_path: Path) -> None:
        """SANDBOX environment must use DHAN_SANDBOX_CLIENT_ID."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_SANDBOX_CLIENT_ID=sandbox_client\n"
            "DHAN_SANDBOX_ACCESS_TOKEN=sandbox_token\n"
            "DHAN_ENVIRONMENT=SANDBOX\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)

        assert settings.is_sandbox is True
        assert settings.is_live is False
        assert settings.client_id == "sandbox_client"


# ── Test 2: Missing required fields raise error ─────────────────────────

class TestMissingRequiredFields:
    """Verify missing required fields raise ValidationError."""

    def test_validate_config_fails_missing_client_id(self, tmp_path: Path) -> None:
        """Missing DHAN_CLIENT_ID must raise ValueError."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_ACCESS_TOKEN=some_token\n"
        )

        with pytest.raises(ValueError, match="DHAN_CLIENT_ID is required"):
            DhanSettingsLoader.from_env(env_path=env_file)

    def test_validate_config_fails_invalid_environment(self, tmp_path: Path) -> None:
        """Invalid DHAN_ENVIRONMENT must raise ValueError."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=test_client\n"
            "DHAN_ENVIRONMENT=INVALID_ENV\n"
        )

        with pytest.raises(ValueError, match="DHAN_ENVIRONMENT must be one of"):
            DhanSettingsLoader.from_env(env_path=env_file)


# ── Test 3: Invalid values behavior ─────────────────────────────────────

class TestInvalidValues:
    """Verify invalid values behavior."""

    def test_validate_config_accepts_negative_http_timeout(self, tmp_path: Path) -> None:
        """Negative http_timeout is parsed as float (loader uses _get_float which returns default on error)."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=test_client\n"
            "DHAN_HTTP_TIMEOUT=-5.0\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)
        assert isinstance(settings.http_timeout, float)
        assert settings.http_timeout == -5.0

    def test_validate_config_fails_empty_client_id(self, tmp_path: Path) -> None:
        """Empty DHAN_CLIENT_ID must raise ValueError."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=\n"
            "DHAN_ACCESS_TOKEN=token\n"
        )

        with pytest.raises(ValueError, match="DHAN_CLIENT_ID is required"):
            DhanSettingsLoader.from_env(env_path=env_file)

    def test_validate_config_defaults_on_non_numeric_timeout(self, tmp_path: Path) -> None:
        """Non-numeric HTTP_TIMEOUT defaults to 15.0 (_get_float returns default on parse error)."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=test_client\n"
            "DHAN_HTTP_TIMEOUT=not_a_number\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)
        assert settings.http_timeout == 15.0  # default


# ── Test 4: Bootstrap uses validation on create ─────────────────────────

class TestBootstrapValidationIntegration:
    """Verify bootstrap_gateway validates config before creating gateway."""

    def test_bootstrap_fails_on_invalid_config(self, tmp_path: Path, caplog) -> None:
        """bootstrap_gateway must fail fast on invalid config."""
        import logging

        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_ACCESS_TOKEN=some_token\n"
            # Missing DHAN_CLIENT_ID
        )

        from domain.ports.bootstrap import BootstrapStatus
        from infrastructure.gateway.factory import bootstrap_gateway

        with caplog.at_level(logging.ERROR):
            result = bootstrap_gateway(
                "dhan",
                env_path=env_file,
                load_instruments=False,
                skip_auth_probe=True,
            )
        assert not result.ok
        assert result.status == BootstrapStatus.FAILED
        assert result.gateway is None
        assert "DHAN_CLIENT_ID" in caplog.text

    def test_bootstrap_creates_gateway_with_valid_config(self, tmp_path: Path) -> None:
        """bootstrap_gateway must succeed with valid config (transport-only, fake token)."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=test_client\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
        )

        from infrastructure.gateway.factory import bootstrap_gateway

        result = bootstrap_gateway(
            "dhan",
            env_path=env_file,
            load_instruments=False,
            skip_auth_probe=True,
        )
        assert result.ok and result.gateway is not None
        result.gateway.close()


# ── Test 5: Validation error messages clear ─────────────────────────────

class TestValidationErrorMessageClarity:
    """Verify ValidationError messages are human-readable and indicate which field failed."""

    def test_validation_error_message_clear_missing_client_id(self, tmp_path: Path) -> None:
        """Error message must mention the missing field."""
        env_file = tmp_path / ".env.test"
        env_file.write_text("DHAN_ACCESS_TOKEN=token\n")

        try:
            DhanSettingsLoader.from_env(env_path=env_file)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            assert "DHAN_CLIENT_ID" in error_msg, f"Error message should mention field: {error_msg}"
            assert "required" in error_msg.lower(), f"Error message should say 'required': {error_msg}"

    def test_validation_error_message_clear_invalid_env(self, tmp_path: Path) -> None:
        """Error message must list valid environments."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=test\n"
            "DHAN_ENVIRONMENT=BAD\n"
        )

        try:
            DhanSettingsLoader.from_env(env_path=env_file)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            assert "DHAN_ENVIRONMENT" in error_msg
            assert "LIVE" in error_msg  # Should mention valid options
            assert "SANDBOX" in error_msg


# ── Test 6: Config defaults applied correctly ───────────────────────────

class TestConfigDefaults:
    """Verify default values are applied when optional fields missing."""

    def test_config_defaults_applied_correctly(self, tmp_path: Path) -> None:
        """Minimal config must have sensible defaults."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=minimal_client\n"
            "DHAN_ACCESS_TOKEN=minimal_token\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)

        # Verify defaults from BrokerSettings
        assert settings.http_timeout == 15.0
        assert settings.enable_retry is True
        assert settings.pool_connections == 50
        assert settings.pool_maxsize == 100

        # Verify defaults from DhanConnectionSettings
        assert settings.environment == "LIVE"
        assert settings.is_live is True
        assert settings.is_sandbox is False
        assert settings.allow_live_orders is False

    def test_config_defaults_override_with_env_vars(self, tmp_path: Path) -> None:
        """Explicit env vars must override defaults."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=override_client\n"
            "DHAN_ACCESS_TOKEN=override_token\n"
            "DHAN_HTTP_TIMEOUT=30.0\n"
            "DHAN_ENABLE_RETRY=false\n"
            "DHAN_POOL_CONNECTIONS=25\n"
            "DHAN_POOL_MAXSIZE=50\n"
            "DHAN_ENVIRONMENT=LIVE\n"
            "DHAN_ALLOW_LIVE_ORDERS=true\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)

        assert settings.http_timeout == 30.0
        assert settings.enable_retry is False
        assert settings.pool_connections == 25
        assert settings.pool_maxsize == 50
        assert settings.environment == "LIVE"
        assert settings.is_live is True
        assert settings.allow_live_orders is True

    def test_config_boolean_parsing(self, tmp_path: Path) -> None:
        """Boolean env vars must parse correctly for various representations."""
        env_file = tmp_path / ".env.test"
        env_file.write_text(
            "DHAN_CLIENT_ID=bool_client\n"
            "DHAN_ACCESS_TOKEN=bool_token\n"
            "DHAN_ENABLE_RETRY=yes\n"
            "DHAN_ALLOW_LIVE_ORDERS=1\n"
        )

        settings = DhanSettingsLoader.from_env(env_path=env_file)
        assert settings.enable_retry is True
        assert settings.allow_live_orders is True

    def test_config_from_dict(self) -> None:
        """from_dict must work for dictionary-based config with DHAN prefix."""
        values = {
            "DHAN.clientId": "dict_client",
            "DHAN.accessToken": "dict_token",
            "DHAN.httpTimeout": "20.0",
            "DHAN.enableRetry": "true",
        }

        settings = DhanSettingsLoader.from_dict(values)

        assert settings.client_id == "dict_client"
        assert settings.access_token == "dict_token"
        assert settings.http_timeout == 20.0
        assert settings.enable_retry is True

    def test_config_from_dict_missing_client_id(self) -> None:
        """from_dict must fail if clientId is missing."""
        values = {
            "DHAN.accessToken": "dict_token",
        }

        with pytest.raises(ValueError, match="dhan.clientId is required"):
            DhanSettingsLoader.from_dict(values)
