"""Dhan-specific resilience configuration — extracted from DhanBroker.__init__.

Provides injectable resilience settings (rate limiters, circuit breakers,
retry executors) so tests and alternative deployments can override defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from brokers.common.resilience.backoff import ExponentialBackoff
from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter, RateLimitConfig
from brokers.common.resilience.retry import RetryConfig, RetryExecutor

_BACKOFF_PRESETS: dict[str, dict] = {
    "orders": {"base_delay_ms": 500, "max_delay_ms": 5000},
    "quotes": {"base_delay_ms": 200, "max_delay_ms": 1000},
    "data": {"base_delay_ms": 200, "max_delay_ms": 2000},
}


@dataclass
class DhanResilienceConfig:
    """Resilience settings for Dhan broker.

    Provides factory methods to build rate limiters, circuit breakers,
    and retry executors with Dhan-appropriate defaults.
    """

    rate_limits: dict[str, RateLimitConfig] = field(default_factory=dict)
    circuit_breaker_configs: dict[str, CircuitBreakerConfig] = field(default_factory=dict)
    retry_configs: dict[str, RetryConfig] = field(default_factory=dict)

    @classmethod
    def default(cls) -> DhanResilienceConfig:
        return cls(
            rate_limits={
                "orders": RateLimitConfig(rate_per_second=10, capacity=10),
                "quotes": RateLimitConfig(rate_per_second=1, capacity=1),
                "data": RateLimitConfig(rate_per_second=5, capacity=20),
            },
            circuit_breaker_configs={
                "orders": CircuitBreakerConfig(failure_threshold=5, open_duration_ms=30_000),
                "quotes": CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                "data": CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
            },
            retry_configs={
                "orders": RetryConfig(max_attempts=3),
                "quotes": RetryConfig(max_attempts=2),
                "data": RetryConfig(max_attempts=2),
            },
        )

    def build_rate_limiter(self) -> MultiBucketRateLimiter:
        return MultiBucketRateLimiter(self.rate_limits)

    def build_circuit_breakers(self) -> dict[str, CircuitBreaker]:
        return {
            name: CircuitBreaker(f"dhan-{name}", config)
            for name, config in self.circuit_breaker_configs.items()
        }

    def build_executors(
        self,
        rate_limiter: MultiBucketRateLimiter,
        circuit_breakers: dict[str, CircuitBreaker],
    ) -> dict[str, RetryExecutor]:
        executors: dict[str, RetryExecutor] = {}
        for name in self.retry_configs:
            backoff_params = _BACKOFF_PRESETS.get(
                name, {"base_delay_ms": 200, "max_delay_ms": 2000}
            )
            executors[name] = RetryExecutor(
                config=self.retry_configs[name],
                circuit_breaker=circuit_breakers.get(name),
                rate_limiter=rate_limiter,
                rate_limit_category=name,
                backoff=ExponentialBackoff(**backoff_params),
            )
        return executors
