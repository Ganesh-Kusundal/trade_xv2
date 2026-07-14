"""Dhan-specific resilience configuration and wiring.

Re-exports circuit breaker, retry executor, and the canonical rate limiter
(pre-configured for Dhan API endpoint categories via brokers.common).
"""

from __future__ import annotations

from infrastructure.resilience._metrics import (
    DhanRateLimiterMetrics,
)
from infrastructure.resilience.rate_limiter import (
    create_rate_limiter,
)
from brokers.dhan.resilience.circuit_breaker import (
    DhanCircuitBreakerFactory,
    create_circuit_breakers,
)
from brokers.dhan.resilience.retry_executor import (
    DhanRetryExecutorFactory,
    DhanRetryPolicy,
    create_retry_executor,
)

# Backward-compatible alias: the per-broker factory module was removed and its
# responsibilities folded into the canonical create_rate_limiter("dhan").
class DhanRateLimiterFactory:
    """Thin compatibility shim over the canonical rate-limiter factory."""

    @staticmethod
    def create() -> "MultiBucketRateLimiter":
        return create_rate_limiter("dhan")

    @staticmethod
    def create_config(category: str) -> "RateLimitConfig":
        from infrastructure.resilience.rate_limiter import (
            MultiBucketRateLimiter,
            RateLimitConfig,
        )
        from brokers.dhan.config.capabilities import dhan_capabilities

        for profile in dhan_capabilities().rate_limit_profiles:
            if profile.endpoint_class == category:
                capacity = int(profile.burst_rps) if profile.burst_rps else int(profile.sustained_rps * 2)
                return RateLimitConfig(
                    rate_per_second=float(profile.sustained_rps),
                    capacity=max(capacity, 1),
                )
        return RateLimitConfig(rate_per_second=20.0, capacity=30)


from infrastructure.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
)

__all__ = [
    "DhanCircuitBreakerFactory",
    "DhanRateLimiterFactory",
    "DhanRateLimiterMetrics",
    "DhanRetryExecutorFactory",
    "DhanRetryPolicy",
    "MultiBucketRateLimiter",
    "RateLimitConfig",
    "create_circuit_breakers",
    "create_rate_limiter",
    "create_retry_executor",
]
