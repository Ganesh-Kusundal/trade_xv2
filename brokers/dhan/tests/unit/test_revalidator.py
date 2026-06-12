"""Tests for DhanTokenRevalidator."""

import time
from unittest.mock import MagicMock, patch

import pytest

from brokers.dhan.auth.auth import DhanHttpError, DhanTokenInfo, DhanTokenManager, DhanTokenState
from brokers.dhan.auth.config import DhanConnectionSettings
from brokers.dhan.auth.revalidator import DhanTokenRevalidator


@pytest.fixture
def settings() -> DhanConnectionSettings:
    return DhanConnectionSettings(
        client_id="client123",
        auth_mode="TOTP_GENERATED",
        refresh_buffer_minutes=10,
    )


@pytest.fixture
def token_manager() -> DhanTokenManager:
    manager = DhanTokenManager(client_id="client123", auth_mode="TOTP_GENERATED")
    manager._current_state = DhanTokenState(
        access_token="live_token",
        expiry_epoch_ms=int(time.time() * 1000) + 3_600_000,
        issued_at_epoch_ms=int(time.time() * 1000),
        source="TOTP_GENERATED",
    )
    return manager


def test_run_once_updates_cached_expiry(token_manager, settings):
    auth_client = MagicMock()
    auth_client.fetch_profile.return_value = DhanTokenInfo(
        valid=True,
        expiry_epoch_ms=int(time.time() * 1000) + 7_200_000,
        refresh_recommended=False,
    )
    revalidator = DhanTokenRevalidator(token_manager, auth_client, settings)

    assert revalidator.run_once() is True
    assert token_manager._current_state.expiry_epoch_ms == auth_client.fetch_profile.return_value.expiry_epoch_ms


def test_run_once_invalidates_on_profile_401(token_manager, settings):
    auth_client = MagicMock()
    auth_client.fetch_profile.side_effect = DhanHttpError("profile 401", 401)
    revalidator = DhanTokenRevalidator(token_manager, auth_client, settings)

    assert revalidator.run_once() is False
    assert token_manager._current_state is None


def test_start_and_stop(token_manager, settings):
    revalidator = DhanTokenRevalidator(
        token_manager,
        MagicMock(),
        settings,
        interval_ms=50,
    )
    revalidator.start()
    assert revalidator.is_running()
    revalidator.stop()
    assert not revalidator.is_running()
