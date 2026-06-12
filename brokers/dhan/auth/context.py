"""Dhan adapter context — shared configuration holder.

Holds the resolved settings plus pre-built shared collaborators (resolver,
URL resolver, HTTP client) that every Dhan adapter needs, so adapters can be
constructed with a single context object instead of each receiving
individual dependencies individually.

Design reference: Trade_J ``DhanAdapterContext`` (the shared container that
wires ``DhanRestOrderClient``, ``DhanMarketDataClient``, etc.).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.alerts import DhanConditionalAlertProvider
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.auth.urls import DhanApiUrlResolver
from brokers.dhan.mapper.instruments import DhanInstrumentResolver
from brokers.dhan.risk import DhanSessionRiskProvider
from brokers.dhan.websocket.market_data import DhanMarketFeedWebSocketClient
from brokers.dhan.websocket.order_stream import DhanOrderStreamWebSocketClient


class DhanAdapterContext:
    """Shared context that wires all Dhan adapters together.

    Usage::

        context = DhanAdapterContext(
            settings=settings,
            token_provider=lambda: token_manager.get_access_token(),
        )
        order_client = DhanRestOrderClient(
            http_client=context.http_client,
            ...
        )
    """

    def __init__(
        self,
        settings: Any,
        token_provider: Callable[[], str],
        *,
        timeout_seconds: int = 15,
        session: Any | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._timeout_seconds = timeout_seconds
        self._session = session

        # Pre-build shared singletons
        self._url_resolver = DhanApiUrlResolver(settings)
        self._http_client = DhanAuthenticatedHttpClient(
            token_provider=token_provider,
            settings=settings,
            timeout_seconds=timeout_seconds,
            session=session,
        )
        self._instrument_resolver = DhanInstrumentResolver()
        self._websocket_client: DhanMarketFeedWebSocketClient | None = None
        self._order_stream_client: DhanOrderStreamWebSocketClient | None = None
        self._risk_provider: DhanSessionRiskProvider | None = None
        self._alert_provider: DhanConditionalAlertProvider | None = None

    # ── Read-only access ─────────────────────────────────────────────

    @property
    def settings(self) -> Any:
        """Resolved connection settings."""
        return self._settings

    @property
    def token_provider(self) -> Callable[[], str]:
        """Callable returning the current valid access token."""
        return self._token_provider

    @property
    def url_resolver(self) -> DhanApiUrlResolver:
        return self._url_resolver

    @property
    def http_client(self) -> DhanAuthenticatedHttpClient:
        return self._http_client

    @property
    def instrument_resolver(self) -> DhanInstrumentResolver:
        return self._instrument_resolver

    @property
    def websocket_client(self) -> DhanMarketFeedWebSocketClient:
        """Get or create WebSocket client for real-time market data."""
        if self._websocket_client is None:
            self._websocket_client = DhanMarketFeedWebSocketClient(
                url_resolver=self._url_resolver,
                token_provider=self._token_provider,
                settings=self._settings,
                timeout_seconds=self._timeout_seconds,
            )
        return self._websocket_client

    @property
    def order_stream_client(self) -> DhanOrderStreamWebSocketClient:
        """Get or create WebSocket client for order stream."""
        if self._order_stream_client is None:
            self._order_stream_client = DhanOrderStreamWebSocketClient(
                url_resolver=self._url_resolver,
                token_provider=self._token_provider,
                settings=self._settings,
                timeout_seconds=self._timeout_seconds,
            )
        return self._order_stream_client

    @property
    def risk_provider(self) -> DhanSessionRiskProvider:
        """Get or create session risk provider."""
        if self._risk_provider is None:
            self._risk_provider = DhanSessionRiskProvider(
                http_client=self._http_client,
                settings=self._settings,
                url_resolver=self._url_resolver,
                retry_executor=self.make_retry_executor("risk"),
                websocket_client=self._websocket_client,
            )
        return self._risk_provider

    @property
    def alert_provider(self) -> DhanConditionalAlertProvider:
        """Get or create conditional alert provider."""
        if self._alert_provider is None:
            self._alert_provider = DhanConditionalAlertProvider(
                http_client=self._http_client,
                settings=self._settings,
                url_resolver=self._url_resolver,
                retry_executor=self.make_retry_executor("alerts"),
                websocket_client=self._websocket_client,
            )
        return self._alert_provider

    # ── Adapter factory helpers ──────────────────────────────────────

    def make_retry_executor(self, category: str) -> RetryExecutor:
        """Build a RetryExecutor for the given rate-limit bucket.

        Retry policies are derived from the context's settings with sensible
        defaults that match Trade_J's channel separation::

            "orders"  -> 3 retries, 10 RPS bucket
            "quotes"  -> 2 retries, 1  RPS bucket
            "data"    -> 2 retries, 5  RPS bucket
        """
        from brokers.common.resilience.backoff import ExponentialBackoff
        from brokers.common.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )
        from brokers.common.resilience.rate_limiter import (
            MultiBucketRateLimiter,
            RateLimitConfig,
        )
        from brokers.common.resilience.retry import RetryConfig

        _CONFIGS: dict[str, tuple[RetryConfig, CircuitBreakerConfig, RateLimitConfig]] = {
            "orders": (
                RetryConfig(max_attempts=3),
                CircuitBreakerConfig(failure_threshold=5, open_duration_ms=30_000),
                RateLimitConfig(rate_per_second=10, capacity=10),
            ),
            "quotes": (
                RetryConfig(max_attempts=2),
                CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                RateLimitConfig(rate_per_second=1, capacity=1),
            ),
            "data": (
                RetryConfig(max_attempts=2),
                CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                RateLimitConfig(rate_per_second=5, capacity=20),
            ),
        }
        retry_cfg, cb_cfg, rl_cfg = _CONFIGS.get(
            category,
            (
                RetryConfig(max_attempts=2),
                CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                RateLimitConfig(rate_per_second=5, capacity=20),
            ),
        )
        return RetryExecutor(
            config=retry_cfg,
            circuit_breaker=CircuitBreaker(f"dhan-{category}", cb_cfg),
            rate_limiter=MultiBucketRateLimiter({category: rl_cfg}),
            rate_limit_category=category,
            backoff=ExponentialBackoff(base_delay_ms=500, max_delay_ms=5000),
        )
