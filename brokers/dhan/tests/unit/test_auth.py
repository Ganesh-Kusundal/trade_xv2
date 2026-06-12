"""Tests for Dhan authentication — TOTP generation and token lifecycle.

Maps to Trade_J's DhanTotpGeneratorUnitTest, DhanAuthClientUnitTest,
DhanTokenManagerUnitTest.
"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from brokers.common.core.auth import TotpGenerator
from brokers.dhan.auth.auth import (
    DhanAuthClient,
    DhanAuthRejected,
    DhanHttpError,
    DhanTokenInfo,
    DhanTokenManager,
    DhanTokenState,
    read_secret_file,
)


class TestTotpGenerator:
    """Tests for TotpGenerator (maps to Trade_J's DhanTotpGenerator)."""

    def test_current_code_returns_6_digits(self):
        gen = TotpGenerator()
        code = gen.current_code("JBSWY3DPEHPK3PXP")
        assert len(code) == 6
        assert code.isdigit()

    def test_code_at_specific_time(self):
        gen = TotpGenerator()
        secret = "JBSWY3DPEHPK3PXP"
        timestamp = 1700000000.0

        code1 = gen.code_at(secret, timestamp)
        code2 = gen.code_at(secret, timestamp)

        # Same timestamp should produce same code
        assert code1 == code2

    def test_code_changes_over_time(self):
        gen = TotpGenerator()
        secret = "JBSWY3DPEHPK3PXP"

        code1 = gen.code_at(secret, 1700000000.0)
        code2 = gen.code_at(secret, 1700000030.0)  # 30 seconds later

        # Different time step should produce different code
        assert code1 != code2

    def test_blank_secret_raises(self):
        gen = TotpGenerator()
        with pytest.raises(ValueError, match="blank"):
            gen.current_code("")

    def test_whitespace_only_secret_raises(self):
        gen = TotpGenerator()
        with pytest.raises(ValueError, match="blank"):
            gen.current_code("   ")

    def test_invalid_base32_raises(self):
        gen = TotpGenerator()
        with pytest.raises(ValueError, match="Invalid Base32"):
            gen.current_code("12345!")

    def test_handles_dashes_and_spaces(self):
        gen = TotpGenerator()
        # These should be equivalent after normalization
        code1 = gen.current_code("JBSWY3DPEHPK3PXP")
        code2 = gen.current_code("JBSWY-3DPE-HPK3P-XP")
        assert code1 == code2


class TestDhanTokenState:
    """Tests for DhanTokenState dataclass."""

    def test_creation(self):
        state = DhanTokenState(
            access_token="test_token",
            expiry_epoch_ms=1700000000000,
            issued_at_epoch_ms=1699999000000,
            source="TOTP_GENERATED",
        )
        assert state.access_token == "test_token"
        assert state.source == "TOTP_GENERATED"

    def test_source_types(self):
        for source in ["STATIC", "TOTP_GENERATED", "WEB_RENEWABLE", "BOOTSTRAP"]:
            state = DhanTokenState(
                access_token="tok",
                expiry_epoch_ms=0,
                issued_at_epoch_ms=0,
                source=source,
            )
            assert state.source == source


class TestDhanTokenInfo:
    """Tests for DhanTokenInfo dataclass."""

    def test_valid_token(self):
        info = DhanTokenInfo(
            valid=True,
            expiry_epoch_ms=int(time.time() * 1000) + 3600000,
            refresh_recommended=False,
        )
        assert info.valid is True
        assert info.refresh_recommended is False

    def test_expired_token(self):
        info = DhanTokenInfo(
            valid=False,
            expiry_epoch_ms=int(time.time() * 1000) - 3600000,
            refresh_recommended=False,
        )
        assert info.valid is False


class TestDhanAuthClient:
    """Tests for DhanAuthClient HTTP operations."""

    def test_generate_via_totp_success(self):
        client = DhanAuthClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "accessToken": "new_access_token",
                "expiryTime": "2026-12-31T23:59:59",
            },
        }

        with patch.object(client._session, "post", return_value=mock_response):
            state = client.generate_via_totp("client123", "1234", "123456")

            assert state.access_token == "new_access_token"
            assert state.source == "TOTP_GENERATED"
            assert state.expiry_epoch_ms > 0

    def test_generate_via_totp_rejects_blank_pin(self):
        client = DhanAuthClient()
        with pytest.raises(DhanAuthRejected):
            client.generate_via_totp("client123", "", "123456")

    def test_generate_via_totp_rate_limited(self):
        client = DhanAuthClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "error",
            "message": "Please try once every 2 minutes",
        }

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(DhanAuthRejected) as exc_info:
                client.generate_via_totp("client123", "1234", "123456")
            assert exc_info.value.rate_limited is True

    def test_renew_token_success(self):
        client = DhanAuthClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "accessToken": "renewed_token",
                "expiryTime": "2026-12-31T23:59:59.123",
            },
        }

        with patch.object(client._session, "post", return_value=mock_response):
            state = client.renew_token("client123", "old_token")

            assert state.access_token == "renewed_token"
            assert state.source == "WEB_RENEWABLE"

    def test_fetch_profile_success(self):
        client = DhanAuthClient()
        future_time = datetime.now() + timedelta(hours=1)
        expiry_str = future_time.strftime("%d/%m/%Y %H:%M")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tokenValidity": expiry_str,
        }

        with patch.object(client._session, "get", return_value=mock_response):
            info = client.fetch_profile("valid_token")

            assert info.valid is True
            assert info.refresh_recommended is False

    def test_fetch_profile_missing_token_validity(self):
        client = DhanAuthClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(client._session, "get", return_value=mock_response):
            with pytest.raises(ValueError, match="tokenValidity"):
                client.fetch_profile("token")

    def test_http_error_raises(self):
        client = DhanAuthClient()
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(client._session, "post", return_value=mock_response):
            with pytest.raises(DhanHttpError) as exc_info:
                client.generate_via_totp("client123", "1234", "123456")
            assert exc_info.value.status_code == 500


class TestDhanTokenManager:
    """Tests for DhanTokenManager lifecycle."""

    def test_static_mode_returns_configured_token(self):
        manager = DhanTokenManager(
            client_id="client123",
            access_token="static_token",
            auth_mode="STATIC",
        )
        assert manager.get_access_token() == "static_token"

    def test_static_mode_raises_without_token(self):
        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="STATIC",
        )
        with pytest.raises(ValueError, match="not configured"):
            manager.get_access_token()

    def test_totp_mode_generates_token(self):
        manager = DhanTokenManager(
            client_id="client123",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
            auth_mode="TOTP_GENERATED",
        )

        mock_client = MagicMock()
        mock_client.generate_via_totp.return_value = DhanTokenState(
            access_token="totp_token",
            expiry_epoch_ms=int(time.time() * 1000) + 3600000,
            issued_at_epoch_ms=int(time.time() * 1000),
            source="TOTP_GENERATED",
        )

        with patch.object(manager, "_auth_client", mock_client):
            manager.ensure_valid()
            assert manager.get_access_token() == "totp_token"
            mock_client.generate_via_totp.assert_called_once()

    def test_totp_mode_requires_pin_and_secret(self):
        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="TOTP_GENERATED",
        )

        with pytest.raises(ValueError, match="pin and totp_secret required"):
            manager.ensure_valid()

    def test_web_renewable_mode_renews_token(self):
        manager = DhanTokenManager(
            client_id="client123",
            access_token="old_token",
            auth_mode="WEB_RENEWABLE",
        )

        mock_client = MagicMock()
        # Bootstrap token adoption: profile shows valid but refresh recommended
        mock_client.fetch_profile.return_value = DhanTokenInfo(
            valid=True,
            expiry_epoch_ms=int(time.time() * 1000) + 60000,  # expires in 1 min
            refresh_recommended=True,
        )
        mock_client.renew_token.return_value = DhanTokenState(
            access_token="renewed_token",
            expiry_epoch_ms=int(time.time() * 1000) + 3600000,
            issued_at_epoch_ms=int(time.time() * 1000),
            source="WEB_RENEWABLE",
        )

        with patch.object(manager, "_auth_client", mock_client):
            manager.ensure_valid()
            # Bootstrap token was adopted (valid but refresh recommended)
            assert manager._current_state.access_token == "old_token"
            # Requesting token triggers renewal since the current one is close to expiry
            assert manager.get_access_token() == "renewed_token"
            mock_client.fetch_profile.assert_called()

    def test_invalidate_clears_state(self):
        manager = DhanTokenManager(
            client_id="client123",
            access_token="token",
            auth_mode="WEB_RENEWABLE",
        )
        manager._current_state = DhanTokenState(
            access_token="token",
            expiry_epoch_ms=int(time.time() * 1000) + 3600000,
            issued_at_epoch_ms=int(time.time() * 1000),
            source="BOOTSTRAP",
        )

        manager.invalidate()
        assert manager._current_state is None

    def test_cooldown_prevents_rapid_acquisition(self):
        manager = DhanTokenManager(
            client_id="client123",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
            auth_mode="TOTP_GENERATED",
        )

        # Simulate recent acquisition attempt
        manager._last_acquisition_attempt_ms = int(time.time() * 1000)

        with pytest.raises(DhanAuthRejected, match="cooldown"):
            manager.ensure_valid()

    def test_token_persistence(self, tmp_path):
        state_file = tmp_path / "token_state.json"
        manager = DhanTokenManager(
            client_id="client123",
            access_token="bootstrap_token",
            auth_mode="WEB_RENEWABLE",
            token_state_file=state_file,
        )

        mock_client = MagicMock()
        mock_client.fetch_profile.return_value = DhanTokenInfo(
            valid=True,
            expiry_epoch_ms=int(time.time() * 1000) + 3600000,
            refresh_recommended=False,
        )

        with patch.object(manager, "_auth_client", mock_client):
            manager.ensure_valid()

            # Verify file was written
            assert state_file.exists()
            data = json.loads(state_file.read_text())
            assert data["access_token"] == "bootstrap_token"
            assert data["source"] == "BOOTSTRAP"

    def test_load_persisted_state(self, tmp_path):
        state_file = tmp_path / "token_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "access_token": "persisted_token",
                    "expiry_epoch_ms": int(time.time() * 1000) + 3600000,
                    "issued_at_epoch_ms": int(time.time() * 1000),
                    "source": "TOTP_GENERATED",
                }
            )
        )

        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="TOTP_GENERATED",
            token_state_file=state_file,
        )

        # State should be loaded from file
        assert manager._current_state is not None
        assert manager._current_state.access_token == "persisted_token"


class TestReadSecretFile:
    """Tests for read_secret_file utility."""

    def test_read_secret_success(self, tmp_path):
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("  my_secret_value  \n")

        result = read_secret_file(secret_file, "test")
        assert result == "my_secret_value"

    def test_read_secret_missing_file(self, tmp_path):
        missing = tmp_path / "missing.txt"
        with pytest.raises(ValueError, match="not found"):
            read_secret_file(missing, "test")

    def test_read_secret_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            read_secret_file(empty_file, "test")

    def test_read_secret_none_path(self):
        with pytest.raises(ValueError, match="not configured"):
            read_secret_file(None, "test")


class TestResolveToWire:
    def test_resolve_to_wire_reliance(self, tmp_path, real_csv_path):
        from brokers.dhan.instrument_service import InstrumentService

        service = InstrumentService(cache_dir=tmp_path / "instr")
        service.load_snapshot(real_csv_path)
        resolved = service.resolve_to_wire("RELIANCE", "NSE")
        assert resolved.security_id == "2885"
        assert resolved.wire_segment == "NSE_EQ"
        assert resolved.canonical_exchange == "NSE"

    def test_resolve_pre_resolved_security_id(self, tmp_path, real_csv_path):
        from brokers.dhan.instrument_service import InstrumentService

        service = InstrumentService(cache_dir=tmp_path / "instr")
        service.load_snapshot(real_csv_path)
        resolved = service.resolve_to_wire("2885", "NSE")
        assert resolved.security_id == "2885"
        assert resolved.wire_segment == "NSE_EQ"


class TestDhanTokenManagerLifecycleExtras:
    def test_ensure_valid_and_get_reuses_reusable_token(self):
        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="TOTP_GENERATED",
        )
        manager._current_state = DhanTokenState(
            access_token="cached_token",
            expiry_epoch_ms=int(time.time() * 1000) + 3_600_000,
            issued_at_epoch_ms=int(time.time() * 1000),
            source="TOTP_GENERATED",
        )
        assert manager.ensure_valid_and_get() == "cached_token"

    def test_update_cached_expiry(self):
        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="TOTP_GENERATED",
        )
        manager._current_state = DhanTokenState(
            access_token="tok",
            expiry_epoch_ms=1_000,
            issued_at_epoch_ms=500,
            source="TOTP_GENERATED",
        )
        assert manager.update_cached_expiry(9_999)
        assert manager._current_state.expiry_epoch_ms == 9_999
        assert manager._current_state.access_token == "tok"

    def test_validate_persisted_token_invalidates_on_profile_401(self):
        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="TOTP_GENERATED",
        )
        manager._current_state = DhanTokenState(
            access_token="dead_token",
            expiry_epoch_ms=int(time.time() * 1000) + 3_600_000,
            issued_at_epoch_ms=int(time.time() * 1000),
            source="TOTP_GENERATED",
        )
        mock_client = MagicMock()
        mock_client.fetch_profile.side_effect = DhanHttpError(
            "Profile fetch failed: HTTP 401", 401
        )
        with patch.object(manager, "_auth_client", mock_client):
            manager.validate_persisted_token_at_startup()
        assert manager._current_state is None

    def test_invalidate_generation_cas(self):
        manager = DhanTokenManager(
            client_id="client123",
            auth_mode="TOTP_GENERATED",
        )
        manager._current_state = DhanTokenState(
            access_token="tok",
            expiry_epoch_ms=int(time.time() * 1000) + 3_600_000,
            issued_at_epoch_ms=int(time.time() * 1000),
            source="TOTP_GENERATED",
        )
        gen = manager.token_generation_id()
        assert manager.invalidate_generation(gen) is True
        assert manager._current_state is None
        assert manager.invalidate_generation(gen) is False
