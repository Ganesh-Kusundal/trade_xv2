"""Dhan-specific resilience configuration and wiring.

Re-exports circuit breaker, retry executor, and rate limiter
pre-configured for Dhan API endpoint categories.
"""

from __future__ import annotations

from brokers.dhan.resilience.circuit_breaker import (
    DhanCircuitBreakerFactory,
    create_circuit_breakers,
)
from brokers.dhan.resilience.rate_limiter import (
    DhanRateLimiterFactory,
    create_rate_limiter,
)
from brokers.dhan.resilience.retry_executor import (
    DhanRetryPolicy,
    DhanRetryExecutorFactory,
    create_retry_executor,
)

__all__ = [
    "DhanCircuitBreakerFactory",
    "create_circuit_breakers",
    "DhanRateLimiterFactory",
    "create_rate_limiter",
    "DhanRetryPolicy",
    "DhanRetryExecutorFactory",
    "create_retry_executor",
]
