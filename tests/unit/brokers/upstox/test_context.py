"""Tests for UpstoxAdapterContext."""

from __future__ import annotations

from brokers.providers.upstox.auth.config import UpstoxConnectionSettings
from brokers.providers.upstox.auth.context import UpstoxAdapterContext
from brokers.providers.upstox.auth.http import UpstoxHttpClient
from brokers.providers.upstox.auth.oauth_client import UpstoxOAuthClient
from brokers.providers.upstox.auth.token_manager import UpstoxTokenManager
from brokers.providers.upstox.auth.urls import UpstoxApiUrlResolver
from infrastructure.resilience.rate_limiter import MultiBucketRateLimiter


def _settings() -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="cid",
        client_secret="sec",
        access_token="abc",
        auth_mode="STATIC",
        environment="LIVE",
        algo_name="alpha",
    )


class TestUpstoxAdapterContext:
    def test_basic_wiring(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        assert ctx.settings is s
        assert ctx.token_provider() == "abc"
        assert isinstance(ctx.url_resolver, UpstoxApiUrlResolver)
        assert isinstance(ctx.http_client, UpstoxHttpClient)
        assert isinstance(ctx.oauth_client, UpstoxOAuthClient)
        assert isinstance(ctx.token_manager, UpstoxTokenManager)

    def test_http_client_uses_settings_algo(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        assert ctx.http_client.settings.algo_name == "alpha"

    def test_custom_token_manager_passthrough(self):
        s = _settings()
        m = UpstoxTokenManager(s)
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc", token_manager=m)
        assert ctx.token_manager is m

    def test_rate_limiter_is_multi_bucket(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        assert isinstance(ctx.rate_limiter, MultiBucketRateLimiter)
        assert set(ctx.rate_limiter.categories()) == {
            "admin",
            "data",
            "funds",
            "historical",
            "holdings",
            "market_data",
            "option_chain",
            "orders",
            "positions",
            "quotes",
        }

    def test_http_client_shares_context_rate_limiter(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        assert ctx.http_client.rate_limiter is ctx.rate_limiter
