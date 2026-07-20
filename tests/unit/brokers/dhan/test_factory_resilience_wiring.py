"""Regression: Dhan BrokerFactory wires rate limiter and circuit breakers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from brokers.dhan.identity.factory import BrokerFactory
from infrastructure.resilience.rate_limiter import MultiBucketRateLimiter


def test_factory_http_client_has_rate_limiter() -> None:
    factory = BrokerFactory()
    settings = MagicMock()
    settings.client_id = "cid"
    settings.base_url = "https://api.dhan.co"
    settings.http_timeout = 15.0
    settings.enable_retry = True
    settings.resilience_config = None

    auth = MagicMock()
    with patch(
        "brokers.dhan.identity.factory._refresh_via_auth",
        return_value="token",
    ):
        client = factory._create_http_client(
            settings,
            auth,
            "token",
            MagicMock(),
            MagicMock(),
        )

    assert isinstance(client._rate_limiter, MultiBucketRateLimiter)
    assert client._read_circuit_breaker is not None
    assert client._write_circuit_breaker is not None
    assert client._admin_circuit_breaker is not None
    assert "orders" in client._circuit_breakers
