"""Multi-bucket token-bucket rate limiting for broker HTTP."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Mapping

# Logical buckets: sustained_rps, burst_rps used as capacity.
# Values mirrored from venue docs (behavior reference — not copied source).

DHAN_RATE_LIMITS: dict[str, dict[str, float]] = {
    "orders": {"sustained_rps": 10.0, "burst_rps": 20.0},
    "quotes": {"sustained_rps": 10.0, "burst_rps": 20.0},
    "historical": {"sustained_rps": 5.0, "burst_rps": 10.0},
    "admin": {"sustained_rps": 10.0, "burst_rps": 20.0},
}

UPSTOX_RATE_LIMITS: dict[str, dict[str, float]] = {
    "orders": {"sustained_rps": 10.0, "burst_rps": 20.0},
    "quotes": {"sustained_rps": 25.0, "burst_rps": 50.0},
    "historical": {"sustained_rps": 5.0, "burst_rps": 10.0},
    "admin": {"sustained_rps": 10.0, "burst_rps": 20.0},
}


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Frozen profile — legacy max_per_second/burst; also accepts rate_per_second/capacity."""

    max_per_second: float = 10.0
    burst: int = 10

    def __init__(
        self,
        max_per_second: float | None = None,
        burst: int | None = None,
        *,
        rate_per_second: float | None = None,
        capacity: int | None = None,
    ) -> None:
        rate = max_per_second if max_per_second is not None else (
            rate_per_second if rate_per_second is not None else 10.0
        )
        cap = burst if burst is not None else (capacity if capacity is not None else 10)
        object.__setattr__(self, "max_per_second", rate)
        object.__setattr__(self, "burst", int(cap))
        if self.max_per_second <= 0:
            raise ValueError("max_per_second must be positive")
        if self.burst <= 0:
            raise ValueError("burst must be positive")

    @property
    def rate_per_second(self) -> float:
        return self.max_per_second

    @property
    def capacity(self) -> int:
        return self.burst


@dataclass
class _BucketConfig:
    rate_per_second: float = 10.0
    capacity: int = 10

    def __post_init__(self) -> None:
        if self.rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")


class TokenBucketRateLimiter:
    def __init__(self, config: RateLimitConfig | _BucketConfig | None = None) -> None:
        if config is None:
            self.config = _BucketConfig()
        elif isinstance(config, RateLimitConfig):
            self.config = _BucketConfig(
                rate_per_second=config.rate_per_second,
                capacity=config.capacity,
            )
        else:
            self.config = config
        self._tokens = float(self.config.capacity)
        self._last_refill_nanos = time.monotonic_ns()
        self._capacity = float(self.config.capacity)
        self._lock = threading.Lock()
        self._original_rate: float | None = None
        self._reduced_at: float | None = None

    @property
    def rate(self) -> float:
        return self.config.rate_per_second

    @rate.setter
    def rate(self, value: float) -> None:
        with self._lock:
            if self._original_rate is None:
                self._original_rate = self.config.rate_per_second
            self.config.rate_per_second = value

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        if tokens > self._capacity:
            return False
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            sleep_time = min(
                timeout if timeout is not None else 0.001,
                1.0 / self.config.rate_per_second if self.config.rate_per_second > 0 else 0.001,
            )
            time.sleep(max(sleep_time, 0.001))

    def _refill(self) -> None:
        now_ns = time.monotonic_ns()
        elapsed_sec = (now_ns - self._last_refill_nanos) / 1_000_000_000.0
        if elapsed_sec > 0:
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed_sec * self.config.rate_per_second,
            )
            self._last_refill_nanos = now_ns


class MultiBucketRateLimiter:
    def __init__(self, configs: dict[str, RateLimitConfig | _BucketConfig]) -> None:
        self._buckets: dict[str, TokenBucketRateLimiter] = {}
        for k, v in configs.items():
            self._buckets[k] = TokenBucketRateLimiter(v)
        self._categories = tuple(configs.keys())

    def categories(self) -> list[str]:
        return list(self._categories)

    def get_bucket(self, category: str) -> TokenBucketRateLimiter:
        bucket = self._buckets.get(category)
        if bucket is None:
            raise ValueError(f"Unknown category: {category}")
        return bucket

    def _resolve(self, category: str) -> TokenBucketRateLimiter:
        bucket = self._buckets.get(category)
        if bucket is not None:
            return bucket
        fallback = self._buckets.get("admin")
        if fallback is not None:
            return fallback
        if self._buckets:
            return next(iter(self._buckets.values()))
        raise ValueError(f"Unknown category: {category}")

    def acquire(self, category: str, tokens: int = 1, timeout: float | None = None) -> bool:
        return self._resolve(category).acquire(tokens, timeout)

    def reduce_rate(self, category: str, factor: float) -> None:
        bucket = self.get_bucket(category) if category in self._buckets else self._resolve(category)
        bucket.rate = bucket.rate * factor
        bucket._reduced_at = time.monotonic()


def limiter_from_table(table: Mapping[str, Mapping[str, float]]) -> MultiBucketRateLimiter:
    configs: dict[str, _BucketConfig] = {}
    for name, row in table.items():
        configs[name] = _BucketConfig(
            rate_per_second=float(row["sustained_rps"]),
            capacity=int(row["burst_rps"]),
        )
    return MultiBucketRateLimiter(configs)
