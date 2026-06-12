"""Resilience module — rate limiting, circuit breakers, retry with backoff."""

from __future__ import annotations

from brokers.common.resilience.backoff import (
    BackoffStrategy,
    ExponentialBackoff,
    FixedBackoff,
    NoBackoff,
)
from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from brokers.common.resilience.errors import (
    BrokerError,
    CircuitBreakerOpenError,
    NonRetryableError,
    RateLimitError,
    RetryableError,
)
from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
)
from brokers.common.resilience.retry import RetryConfig, RetryExecutor

__all__ = [
    "BackoffStrategy",
    "BrokerError",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "ExponentialBackoff",
    "FixedBackoff",
    "MultiBucketRateLimiter",
    "NoBackoff",
    "NonRetryableError",
    "RateLimitConfig",
    "RateLimitError",
    "RetryConfig",
    "RetryExecutor",
    "RetryableError",
    "TokenBucketRateLimiter",
]
