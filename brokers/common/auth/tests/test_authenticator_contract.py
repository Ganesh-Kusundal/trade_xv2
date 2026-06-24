"""Contract tests for BrokerAuthenticator implementations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.common.auth.registry import BrokerAuthenticator
from brokers.upstox.auth.authenticator import UpstoxAuthenticator


class TestUpstoxAuthenticator:
    @patch("brokers.upstox.auth.authenticator.UpstoxSettingsLoader")
    @patch("brokers.upstox.auth.authenticator.UpstoxTokenManager")
    def test_acquire_returns_access_token_string(self, mock_tm_cls, mock_loader):
        mock_loader.from_env.return_value = MagicMock()
        mock_mgr = mock_tm_cls.return_value
        mock_state = MagicMock()
        mock_state.access_token = "test-access-token"
        mock_mgr.bootstrap.return_value = mock_state

        auth = UpstoxAuthenticator()
        token = auth.acquire()

        assert token == "test-access-token"
        mock_mgr.bootstrap.assert_called_once()

    @patch("brokers.upstox.auth.authenticator.UpstoxSettingsLoader")
    @patch("brokers.upstox.auth.authenticator.UpstoxTokenManager")
    def test_is_authenticated_uses_current_token(self, mock_tm_cls, mock_loader):
        mock_loader.from_env.return_value = MagicMock()
        mock_mgr = mock_tm_cls.return_value
        mock_mgr.current_token.return_value = "live-token"

        auth = UpstoxAuthenticator()
        assert auth.is_authenticated() is True
        mock_mgr.current_token.assert_called()

    @patch("brokers.upstox.auth.authenticator.UpstoxSettingsLoader")
    @patch("brokers.upstox.auth.authenticator.UpstoxTokenManager")
    def test_ensure_valid_calls_token_manager(self, mock_tm_cls, mock_loader):
        mock_loader.from_env.return_value = MagicMock()
        mock_mgr = mock_tm_cls.return_value
        mock_mgr.current_token.return_value = "live-token"

        auth = UpstoxAuthenticator()
        assert auth.ensure_valid() is True
        mock_mgr.ensure_valid.assert_called_once()

    @patch("brokers.upstox.auth.authenticator.UpstoxSettingsLoader")
    @patch("brokers.upstox.auth.authenticator.UpstoxTokenManager")
    def test_satisfies_broker_authenticator_protocol(self, mock_tm_cls, mock_loader):
        mock_loader.from_env.return_value = MagicMock()
        mock_mgr = mock_tm_cls.return_value
        mock_state = MagicMock(access_token="tok")
        mock_mgr.bootstrap.return_value = mock_state
        mock_mgr.current_token.return_value = "tok"

        auth = UpstoxAuthenticator()
        assert isinstance(auth, BrokerAuthenticator)
