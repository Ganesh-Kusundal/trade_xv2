"""Tests for token expiry validation in test skip guards."""

from __future__ import annotations

import base64
import json
import time

from tests.conftest import is_token_expired


def _make_jwt(exp: int | None = None) -> str:
    """Create a fake JWT token with optional expiry claim."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {}
    if exp is not None:
        payload["exp"] = exp

    def encode(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{encode(header)}.{encode(payload)}.signature"


class TestTokenExpiryValidation:
    """Verify that is_token_expired correctly identifies expired tokens."""

    def test_expired_token_returns_true(self):
        """Token with exp in the past should be marked as expired."""
        past = int(time.time()) - 3600  # 1 hour ago
        token = _make_jwt(exp=past)
        assert is_token_expired(token) is True

    def test_valid_token_returns_false(self):
        """Token with exp in the future should be marked as valid."""
        future = int(time.time()) + 3600  # 1 hour from now
        token = _make_jwt(exp=future)
        assert is_token_expired(token) is False

    def test_token_without_exp_returns_false(self):
        """Token without expiry claim should let test run."""
        token = _make_jwt(exp=None)
        assert is_token_expired(token) is False

    def test_empty_string_returns_true(self):
        """Empty token should be treated as expired."""
        assert is_token_expired("") is True

    def test_none_returns_true(self):
        """None token should be treated as expired."""
        assert is_token_expired(None) is True  # type: ignore

    def test_invalid_format_returns_true(self):
        """Non-JWT format should be treated as expired."""
        assert is_token_expired("not-a-jwt") is True
        assert is_token_expired("only.two") is True

    def test_malformed_base64_returns_false(self):
        """Malformed base64 should let test run (fail naturally)."""
        token = "header.!!!invalid!!!.signature"
        # Should return False to let test fail naturally
        assert is_token_expired(token) is False
