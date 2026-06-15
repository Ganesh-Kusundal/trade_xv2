"""Unit tests for WebSocket token provider support."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from brokers.dhan.websocket import _DhanContext


class TestDhanContextTokenProvider:
    def test_static_token(self):
        ctx = _DhanContext("client123", access_token="static_token")
        assert ctx.get_access_token() == "static_token"

    def test_token_provider_callable(self):
        provider = MagicMock(return_value="fresh_token")
        ctx = _DhanContext("client123", access_token_fn=provider)
        token = ctx.get_access_token()
        assert token == "fresh_token"
        provider.assert_called_once()

    def test_provider_fallback_to_static(self):
        provider = MagicMock(side_effect=RuntimeError("provider failed"))
        ctx = _DhanContext("client123", access_token="fallback_token", access_token_fn=provider)
        token = ctx.get_access_token()
        assert token == "fallback_token"

    def test_update_token(self):
        ctx = _DhanContext("client123", access_token="old_token")
        ctx.update_token("new_token")
        assert ctx.get_access_token() == "new_token"

    def test_provider_called_on_each_access(self):
        call_count = 0

        def counting_provider():
            nonlocal call_count
            call_count += 1
            return f"token_{call_count}"

        ctx = _DhanContext("client123", access_token_fn=counting_provider)
        assert ctx.get_access_token() == "token_1"
        assert ctx.get_access_token() == "token_2"
        assert ctx.get_access_token() == "token_3"

    def test_client_id(self):
        ctx = _DhanContext("my_client")
        assert ctx.get_client_id() == "my_client"

    def test_get_dhan_http_returns_none(self):
        ctx = _DhanContext("client123", access_token="token")
        assert ctx.get_dhan_http() is None

    def test_no_token_no_provider(self):
        ctx = _DhanContext("client123")
        assert ctx.get_access_token() == ""
