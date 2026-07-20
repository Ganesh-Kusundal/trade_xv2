"""Shared DI container for Upstox adapters.

Mirrors Trade_J ``UpstoxBrokerConnectionFactory`` — wires all adapters from
the resolved settings + token manager + HTTP client.

Tested contract:

* ``UpstoxAdapterContext(settings=..., token_provider=...)`` constructs a
  context exposing ``settings``, ``token_provider()``, ``url_resolver``,
  ``http_client``, ``oauth_client``, and ``token_manager``.
* ``ctx.http_client.settings.algo_name`` flows through to the auth layer.
* Passing ``token_manager=...`` overrides the auto-built one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from infrastructure.pool.connection_pool import get_connection_pool

from .config import UpstoxConnectionSettings
from .http import UpstoxHttpClient
from .oauth_client import UpstoxOAuthClient
from .token_manager import UpstoxTokenManager
from .urls import UpstoxApiUrlResolver


class UpstoxAdapterContext:
    """DI container for the Upstox adapter stack."""

    def __init__(
        self,
        *,
        settings: UpstoxConnectionSettings,
        token_provider: Callable[[], str],
        token_manager: UpstoxTokenManager | None = None,
        http_session: Any | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._url_resolver = UpstoxApiUrlResolver(settings)

        # Use provided session or get from connection pool
        if http_session is None:
            pool = get_connection_pool()
            http_session = pool.get_session("upstox")

        self._oauth_client = UpstoxOAuthClient(base_url=settings.base_v2)
        self._token_manager = token_manager or UpstoxTokenManager(
            settings=settings, oauth_client=self._oauth_client
        )

        from brokers.upstox.capabilities.snapshot import upstox_capabilities
        from infrastructure.resilience.rate_limiter import create_rate_limiter

        self._rate_limiter = create_rate_limiter("upstox", caps=upstox_capabilities())
        self._http_client = UpstoxHttpClient(
            token_provider=token_provider,
            settings=settings,
            session=http_session,
            rate_limiter=self._rate_limiter,
            on_auth_failure=self._token_manager.try_refresh_on_401,
        )

    @property
    def settings(self) -> UpstoxConnectionSettings:
        return self._settings

    @property
    def token_provider(self) -> Callable[[], str]:
        return self._token_provider

    @property
    def url_resolver(self) -> UpstoxApiUrlResolver:
        return self._url_resolver

    @property
    def http_client(self) -> UpstoxHttpClient:
        return self._http_client

    @property
    def rate_limiter(self) -> Any:
        return self._rate_limiter

    @property
    def oauth_client(self) -> UpstoxOAuthClient:
        return self._oauth_client

    @property
    def token_manager(self) -> UpstoxTokenManager:
        return self._token_manager
