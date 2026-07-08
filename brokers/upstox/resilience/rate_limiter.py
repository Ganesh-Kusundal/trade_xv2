"""Upstox-specific rate limiter with per-category token buckets.

Per-endpoint rate limits based on Upstox API documentation and tuned safety
values (mirrors Trade_J UpstoxRateLimiterFactory):

  - Quotes (market-quote, market indicators): 1 RPS, capacity 1
  - Data (historical candles): 5 RPS, capacity 20
  - Orders (place/modify/cancel): 10 RPS, capacity 10
  - Admin (portfolio, user, login): 10 RPS, capacity 10
"""

from __future__ import annotations

import logging

from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)

QUOTES_RATE_PER_SECOND = 1.0
QUOTES_CAPACITY = 1

DATA_RATE_PER_SECOND = 5.0
DATA_CAPACITY = 20

ORDERS_RATE_PER_SECOND = 10.0
ORDERS_CAPACITY = 10

ADMIN_RATE_PER_SECOND = 10.0
ADMIN_CAPACITY = 10


class UpstoxRateLimiterFactory:
    """Factory for Upstox-specific rate limiters."""

    @staticmethod
    def create_config(category: str) -> RateLimitConfig:
        configs = {
            "quotes": RateLimitConfig(
                rate_per_second=QUOTES_RATE_PER_SECOND,
                capacity=QUOTES_CAPACITY,
            ),
            "data": RateLimitConfig(
                rate_per_second=DATA_RATE_PER_SECOND,
                capacity=DATA_CAPACITY,
            ),
            "orders": RateLimitConfig(
                rate_per_second=ORDERS_RATE_PER_SECOND,
                capacity=ORDERS_CAPACITY,
            ),
            "admin": RateLimitConfig(
                rate_per_second=ADMIN_RATE_PER_SECOND,
                capacity=ADMIN_CAPACITY,
            ),
        }
        config = configs.get(category)
        if config is None:
            logger.warning(
                "unknown_upstox_rate_limit_category",
                extra={"category": category, "defaulting_to": "admin"},
            )
            config = configs["admin"]
        return config

    @staticmethod
    def create() -> MultiBucketRateLimiter:
        configs = {
            "quotes": UpstoxRateLimiterFactory.create_config("quotes"),
            "data": UpstoxRateLimiterFactory.create_config("data"),
            "orders": UpstoxRateLimiterFactory.create_config("orders"),
            "admin": UpstoxRateLimiterFactory.create_config("admin"),
        }
        return MultiBucketRateLimiter(configs)


def create_rate_limiter() -> MultiBucketRateLimiter:
    """Convenience function to create an Upstox rate limiter."""
    return UpstoxRateLimiterFactory.create()
