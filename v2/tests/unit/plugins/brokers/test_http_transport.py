"""HttpTransport — rate-limit acquire + 429 cooldown + auth header."""

from __future__ import annotations

from typing import Any

import pytest

from plugins.brokers.common.rate_limit import MultiBucketRateLimiter, RateLimitConfig
from plugins.brokers.common.transport import HttpTransport, RateLimitExceeded
from shared.errors import AuthenticationError, BrokerError, NetworkError, RateLimitError


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.status = 200
        self.body: Any = {"ok": True}

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        self.calls.append((method, url, kwargs))
        return self.status, self.body


def test_get_acquires_quotes_bucket() -> None:
    limiter = MultiBucketRateLimiter(
        {"quotes": RateLimitConfig(rate_per_second=100.0, capacity=1)}
    )
    client = _FakeClient()
    transport = HttpTransport(
        base_url="https://example.test",
        limiter=limiter,
        token_provider=lambda: "tok",
        client=client,
        bucket_for_path=lambda path, method: "quotes",
    )
    assert transport.get("/quote") == {"ok": True}
    assert client.calls[0][2]["headers"]["Authorization"] == "Bearer tok"
    assert limiter.acquire("quotes", timeout=0.0) is False


def test_429_raises_and_reduces_rate() -> None:
    limiter = MultiBucketRateLimiter(
        {"orders": RateLimitConfig(rate_per_second=10.0, capacity=10)}
    )
    client = _FakeClient()
    client.status = 429
    client.body = {"error": "rate limited"}
    transport = HttpTransport(
        base_url="https://example.test",
        limiter=limiter,
        token_provider=lambda: "tok",
        client=client,
        bucket_for_path=lambda path, method: "orders",
    )
    with pytest.raises(RateLimitExceeded):
        transport.post("/orders", json={})
    assert limiter.get_bucket("orders").rate < 10.0


def _transport(client: _FakeClient, bucket: str = "quotes") -> HttpTransport:
    limiter = MultiBucketRateLimiter({bucket: RateLimitConfig(rate_per_second=100.0, capacity=5)})
    return HttpTransport(
        base_url="https://example.test",
        limiter=limiter,
        token_provider=lambda: "tok",
        client=client,
        bucket_for_path=lambda path, method: bucket,
    )


def test_429_is_a_rate_limit_error() -> None:
    client = _FakeClient()
    client.status = 429
    with pytest.raises(RateLimitError):
        _transport(client).get("/quote")


@pytest.mark.parametrize("status", [401, 403])
def test_401_403_are_authentication_errors(status: int) -> None:
    client = _FakeClient()
    client.status = status
    client.body = {"error": "denied"}
    with pytest.raises(AuthenticationError):
        _transport(client).get("/quote")


def test_5xx_is_a_network_error() -> None:
    client = _FakeClient()
    client.status = 503
    client.body = {"error": "unavailable"}
    with pytest.raises(NetworkError):
        _transport(client).get("/quote")


def test_other_4xx_is_a_broker_error() -> None:
    client = _FakeClient()
    client.status = 422
    client.body = {"error": "unprocessable"}
    with pytest.raises(BrokerError):
        _transport(client).get("/quote")


def test_post_uses_orders_bucket_by_default() -> None:
    limiter = MultiBucketRateLimiter(
        {
            "orders": RateLimitConfig(rate_per_second=100.0, capacity=1),
            "quotes": RateLimitConfig(rate_per_second=100.0, capacity=5),
        }
    )
    client = _FakeClient()
    transport = HttpTransport(
        base_url="https://example.test",
        limiter=limiter,
        token_provider=lambda: "t",
        client=client,
    )
    transport.post("/orders", json={"x": 1})
    assert limiter.acquire("orders", timeout=0.0) is False
    assert limiter.acquire("quotes", timeout=0.0) is True
