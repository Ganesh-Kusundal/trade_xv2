"""HttpTransport — rate-limit acquire + 429 cooldown + auth header."""

from __future__ import annotations

from typing import Any

import pytest

from plugins.brokers.common.rate_limit import MultiBucketRateLimiter, RateLimitConfig
from plugins.brokers.common.transport import HttpTransport, RateLimitExceeded


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
