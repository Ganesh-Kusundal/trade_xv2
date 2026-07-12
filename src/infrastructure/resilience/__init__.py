"""Resilience module — rate limiting, circuit breakers, retry with backoff.

Canonical location: ``infrastructure.resilience``.
``tradex.runtime.resilience`` is a backward-compat facade that re-exports this package.
"""

from __future__ import annotations

from infrastructure.resilience.backoff import (
    BackoffStrategy,
    ExponentialBackoff,
    FixedBackoff,
    NoBackoff,
)
from infrastructure.resilience.broker_health_monitor import (
    BrokerHealthMonitor,
    BrokerHealthStatus,
)
from infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from infrastructure.resilience.errors import (
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    CircuitBreakerOpenError,
    ConfigError,
    DataError,
    InstrumentNotFoundError,
    NonRetryableError,
    NotSupportedError,
    OrderError,
    RateLimitError,
    RetryableError,
    TradeXV2Error,
    ValidationError,
)
from infrastructure.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
)
from infrastructure.resilience.retry_executor import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    RetryConfig,
    RetryExecutor,
)

__all__ = [
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    "AuthenticationError",
    "BackoffStrategy",
    "BrokerDegradedError",
    "BrokerError",
    "BrokerHealthMonitor",
    "BrokerHealthStatus",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "ConfigError",
    "DataError",
    "ExponentialBackoff",
    "FixedBackoff",
    "InstrumentNotFoundError",
    "MultiBucketRateLimiter",
    "NoBackoff",
    "NonRetryableError",
    "NotSupportedError",
    "OrderError",
    "RateLimitConfig",
    "RateLimitError",
    "RetryConfig",
    "RetryExecutor",
    "RetryableError",
    "TokenBucketRateLimiter",
    "TradeXV2Error",
    "ValidationError",
]
