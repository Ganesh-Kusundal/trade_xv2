"""Regression tests: mid-session token recovery on HTTP 401/403.

Verifies the legacy-faithful pattern:
1. token_provider is called on every request (active probe, not passive getter)
2. On 401/403, on_auth_failure is invoked; if it returns True the request is
   retried with the refreshed token.
3. If on_auth_failure returns False (refresh itself failed), AuthenticationError
   is raised.
4. If the retry also returns 401, AuthenticationError is raised (no infinite loop).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from plugins.brokers.common.rate_limit import MultiBucketRateLimiter
from plugins.brokers.common.transport import HttpTransport
from shared.errors import AuthenticationError


class _FakeClient:
    """Programmable HTTP client that returns (status, body) per call."""

    def __init__(self, responses: list[tuple[int, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        self.calls.append({"method": method, "url": url, "headers": dict(kwargs.get("headers", {}))})
        if self._responses:
            return self._responses.pop(0)
        return (200, {})


def _make_transport(
    client: _FakeClient,
    *,
    token_provider: Any = lambda: "tok-abc",
    on_auth_failure: Any = None,
) -> HttpTransport:
    limiter = MagicMock(spec=MultiBucketRateLimiter)
    limiter.acquire.return_value = True
    return HttpTransport(
        base_url="https://api.example.com",
        limiter=limiter,
        token_provider=token_provider,
        client=client,
        on_auth_failure=on_auth_failure,
    )


class TestTokenProviderCalledPerRequest:
    """token_provider must be invoked on every request, not cached once."""

    def test_token_provider_called_each_request(self) -> None:
        tokens_returned: list[str] = []
        call_count = 0

        def provider() -> str:
            nonlocal call_count
            call_count += 1
            tok = f"tok-{call_count}"
            tokens_returned.append(tok)
            return tok

        client = _FakeClient([(200, {"ok": True}), (200, {"ok": True})])
        transport = _make_transport(client, token_provider=provider)

        transport.get("/first")
        transport.get("/second")

        assert call_count == 2  # called on BOTH requests
        assert tokens_returned == ["tok-1", "tok-2"]

    def test_latest_token_used_in_headers(self) -> None:
        counter = 0

        def provider() -> str:
            nonlocal counter
            counter += 1
            return f"fresh-token-{counter}"

        client = _FakeClient([(200, {})])
        transport = _make_transport(client, token_provider=provider)

        transport.get("/data")

        auth_header = client.calls[0]["headers"].get("Authorization", "")
        assert "fresh-token-1" in auth_header


class TestOnAuthFailureRetriesOnce:
    """On 401, on_auth_failure is called; if True → retry with new token."""

    def test_401_triggers_reauth_and_retry_succeeds(self) -> None:
        # First call: 401. Second call (after refresh): 200.
        client = _FakeClient([(401, {"error": "token expired"}), (200, {"funds": 1000})])
        reauth_calls = 0

        def reauth() -> bool:
            nonlocal reauth_calls
            reauth_calls += 1
            return True

        tokens = iter(["stale-token", "refreshed-token"])
        transport = _make_transport(
            client,
            token_provider=lambda: next(tokens),
            on_auth_failure=reauth,
        )

        result = transport.get("/funds")

        assert result == {"funds": 1000}
        assert reauth_calls == 1
        assert len(client.calls) == 2
        # Second call should use the refreshed token
        assert "refreshed-token" in client.calls[1]["headers"].get("Authorization", "")

    def test_403_also_triggers_reauth(self) -> None:
        client = _FakeClient([(403, {"error": "forbidden"}), (200, {"ok": True})])
        transport = _make_transport(
            client,
            token_provider=lambda: "tok",
            on_auth_failure=lambda: True,
        )

        result = transport.get("/data")

        assert result == {"ok": True}
        assert len(client.calls) == 2

    def test_401_when_reauth_returns_false_raises(self) -> None:
        client = _FakeClient([(401, {"error": "token expired"})])
        transport = _make_transport(
            client,
            token_provider=lambda: "tok",
            on_auth_failure=lambda: False,  # refresh failed
        )

        with pytest.raises(AuthenticationError, match="401"):
            transport.get("/funds")

        assert len(client.calls) == 1  # no retry

    def test_401_when_no_on_auth_failure_raises(self) -> None:
        client = _FakeClient([(401, {"error": "token expired"})])
        transport = _make_transport(client, token_provider=lambda: "tok")

        with pytest.raises(AuthenticationError, match="401"):
            transport.get("/funds")

    def test_retry_also_401_raises_no_infinite_loop(self) -> None:
        """Even after refresh, if broker still returns 401 → raise, don't loop."""
        client = _FakeClient([(401, {}), (401, {})])
        transport = _make_transport(
            client,
            token_provider=lambda: "tok",
            on_auth_failure=lambda: True,
        )

        with pytest.raises(AuthenticationError, match="401"):
            transport.get("/funds")

        assert len(client.calls) == 2  # exactly 2: original + 1 retry


class TestConnectionWiring:
    """Verify DhanConnection and UpstoxConnection wire ensure_token + reauth."""

    def test_dhan_connection_uses_ensure_token(self) -> None:
        from plugins.brokers.dhan.connection import DhanConnection

        # Verify the method reference is ensure_token, not current
        # We can't fully construct without config, but we can check the source
        import inspect

        source = inspect.getsource(DhanConnection.__init__)
        assert "ensure_token" in source
        assert "on_auth_failure" in source

    def test_upstox_connection_uses_ensure_token(self) -> None:
        from plugins.brokers.upstox.connection import UpstoxConnection

        import inspect

        source = inspect.getsource(UpstoxConnection.__init__)
        assert "ensure_token" in source
        assert "on_auth_failure" in source

    def test_dhan_reauth_on_401_calls_force_refresh(self) -> None:
        from plugins.brokers.dhan.connection import DhanConnection

        conn = DhanConnection.__new__(DhanConnection)
        mock_tokens = MagicMock()
        conn._tokens = mock_tokens

        result = conn._reauth_on_401()

        assert result is True
        mock_tokens.ensure_token.assert_called_once_with(force_refresh=True)

    def test_dhan_reauth_on_401_returns_false_on_failure(self) -> None:
        from plugins.brokers.dhan.connection import DhanConnection

        conn = DhanConnection.__new__(DhanConnection)
        mock_tokens = MagicMock()
        mock_tokens.ensure_token.side_effect = RuntimeError("TOTP cooldown")
        conn._tokens = mock_tokens

        result = conn._reauth_on_401()

        assert result is False

    def test_upstox_reauth_on_401_calls_force_refresh(self) -> None:
        from plugins.brokers.upstox.connection import UpstoxConnection

        conn = UpstoxConnection.__new__(UpstoxConnection)
        mock_tokens = MagicMock()
        conn._tokens = mock_tokens

        result = conn._reauth_on_401()

        assert result is True
        mock_tokens.ensure_token.assert_called_once_with(force_refresh=True)

    def test_upstox_reauth_on_401_returns_false_on_failure(self) -> None:
        from plugins.brokers.upstox.connection import UpstoxConnection

        conn = UpstoxConnection.__new__(UpstoxConnection)
        mock_tokens = MagicMock()
        mock_tokens.ensure_token.side_effect = RuntimeError("refresh failed")
        conn._tokens = mock_tokens

        result = conn._reauth_on_401()

        assert result is False
