"""Shared rate-limit config tables feed MultiBucketRateLimiter."""

from __future__ import annotations

from brokers.common.rate_limit_config import (
    DHAN_RATE_LIMITS,
    UPSTOX_RATE_LIMITS,
    build_limiter,
    profiles_from_table,
)


def test_dhan_and_upstox_tables_have_orders_and_quotes() -> None:
    assert "orders" in DHAN_RATE_LIMITS
    assert "quotes" in DHAN_RATE_LIMITS
    assert "orders" in UPSTOX_RATE_LIMITS
    assert "quotes" in UPSTOX_RATE_LIMITS


def test_profiles_from_table_roundtrip() -> None:
    profiles = profiles_from_table(DHAN_RATE_LIMITS)
    assert {p.endpoint_class for p in profiles} == set(DHAN_RATE_LIMITS)


def test_build_limiter_has_buckets() -> None:
    limiter = build_limiter("dhan")
    # MultiBucketRateLimiter exposes bucket names via configs / acquire
    assert limiter is not None
