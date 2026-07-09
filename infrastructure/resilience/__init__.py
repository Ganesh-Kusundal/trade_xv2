"""Resilience module — rate limiting, circuit breakers, retry with backoff.

Canonical location: ``tradex.runtime.resilience``.
"""

from __future__ import annotations

from infrastructure.resilience.backoff import (  # noqa: F401
    BackoffStrategy,
    ExponentialBackoff,
    FixedBackoff,
    NoBackoff,
)
from infrastructure.resilience.broker_health_monitor import (  # noqa: F401
    BrokerHealthMonitor,
    BrokerHealthStatus,
)
from infrastructure.resilience.circuit_breaker import (  # noqa: F401
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from infrastructure.resilience.errors import (  # noqa: F401
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
from infrastructure.resilience.rate_limiter import (  # noqa: F401
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
)
from infrastructure.resilience.retry import (  # noqa: F401
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
