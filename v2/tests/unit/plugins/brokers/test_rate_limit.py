"""Multi-bucket rate limiter — acquire, timeout, 429 cooldown."""

from __future__ import annotations

import time

from plugins.brokers.common.rate_limit import (
    DHAN_RATE_LIMITS,
    UPSTOX_RATE_LIMITS,
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
    limiter_from_table,
)


def test_token_bucket_acquires_until_empty() -> None:
    bucket = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=100.0, capacity=2))
    assert bucket.acquire(1, timeout=0.0) is True
    assert bucket.acquire(1, timeout=0.0) is True
    assert bucket.acquire(1, timeout=0.0) is False


def test_token_bucket_refills() -> None:
    bucket = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=50.0, capacity=1))
    assert bucket.acquire(1, timeout=0.0) is True
    assert bucket.acquire(1, timeout=0.05) is True


def test_multi_bucket_separate_categories() -> None:
    limiter = MultiBucketRateLimiter(
        {
            "orders": RateLimitConfig(rate_per_second=100.0, capacity=1),
            "quotes": RateLimitConfig(rate_per_second=100.0, capacity=1),
        }
    )
    assert limiter.acquire("orders", timeout=0.0) is True
    assert limiter.acquire("orders", timeout=0.0) is False
    assert limiter.acquire("quotes", timeout=0.0) is True


def test_multi_bucket_reduce_rate_on_429() -> None:
    limiter = MultiBucketRateLimiter(
        {"orders": RateLimitConfig(rate_per_second=10.0, capacity=10)}
    )
    limiter.reduce_rate("orders", 0.5)
    assert limiter.get_bucket("orders").rate == 5.0


def test_limiter_from_dhan_table() -> None:
    limiter = limiter_from_table(DHAN_RATE_LIMITS)
    assert "orders" in limiter.categories()
    assert limiter.acquire("orders", timeout=1.0) is True


def test_limiter_from_upstox_table() -> None:
    limiter = limiter_from_table(UPSTOX_RATE_LIMITS)
    assert "quotes" in limiter.categories()


def test_unknown_category_falls_back_to_admin() -> None:
    limiter = MultiBucketRateLimiter(
        {
            "admin": RateLimitConfig(rate_per_second=100.0, capacity=2),
            "orders": RateLimitConfig(rate_per_second=100.0, capacity=1),
        }
    )
    assert limiter.acquire("unknown_bucket", timeout=0.0) is True
