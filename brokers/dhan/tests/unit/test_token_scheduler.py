"""Unit tests for TokenRefreshScheduler."""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from brokers.common.core.auth import AuthManager, TokenState, TokenSource
from brokers.dhan.token_scheduler import TokenRefreshScheduler


@pytest.fixture
def mock_auth():
    """Create a mock AuthManager."""
    auth = MagicMock(spec=AuthManager)
    auth.state = TokenState(
        access_token="test_token_123",
        source=TokenSource.TOTP,
    )
    auth.ensure_valid.return_value = True
    return auth


class TestTokenRefreshScheduler:
    def test_start_creates_daemon_thread(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()

    def test_stop_joins_thread(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()
        assert not scheduler.is_running

    def test_start_idempotent(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.start()
        scheduler.start()  # Should not create second thread
        assert scheduler.is_running
        scheduler.stop()

    def test_refresh_now_calls_ensure_valid(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        result = scheduler.refresh_now()
        mock_auth.ensure_valid.assert_called_once_with(buffer_seconds=600)
        assert result is True

    def test_refresh_now_calls_on_refresh(self, mock_auth):
        on_refresh = MagicMock()
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, on_refresh=on_refresh)
        scheduler.refresh_now()
        on_refresh.assert_called_once_with("test_token_123")

    def test_refresh_now_returns_false_on_failure(self, mock_auth):
        mock_auth.ensure_valid.return_value = False
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        result = scheduler.refresh_now()
        assert result is False

    def test_refresh_now_handles_exception(self, mock_auth):
        mock_auth.ensure_valid.side_effect = RuntimeError("auth error")
        on_error = MagicMock()
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, on_error=on_error)
        result = scheduler.refresh_now()
        assert result is False

    def test_background_refresh_increments_count(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=1)
        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()
        assert scheduler.refresh_count >= 1

    def test_custom_buffer_seconds(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, buffer_seconds=300)
        scheduler.refresh_now()
        mock_auth.ensure_valid.assert_called_once_with(buffer_seconds=300)

    def test_custom_interval(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=5)
        assert scheduler._interval == 5

    def test_refresh_count_starts_at_zero(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        assert scheduler.refresh_count == 0

    def test_stop_when_not_started(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.stop()  # Should not raise

    def test_on_error_callback_on_failure(self, mock_auth):
        mock_auth.ensure_valid.side_effect = RuntimeError("boom")
        on_error = MagicMock()
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, on_error=on_error)
        scheduler.refresh_now()
        on_error.assert_called_once()
