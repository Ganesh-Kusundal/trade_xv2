"""Multi-bucket token-bucket rate limiting for broker HTTP.

Extended with rolling-window caps, min_interval enforcement, and 429 cooldown
(matching src/brokers/common/rate_limit_config.py feature parity).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Mapping

# Rate limit tables — extended with min_interval_ms, cooldown_on_429_s, extra_windows
# Values mirrored from src/brokers/common/rate_limit_config.py

DHAN_RATE_LIMITS: dict[str, dict[str, float | tuple[tuple[int, float], ...]]] = {
    "orders": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 130,
        "extra_windows": ((250, 60.0), (7000, 86400.0)),
    },
    "quotes": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 130,
    },
    "historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 130,
    },
    "options_historical": {
        "sustained_rps": 2.0,
        "burst_rps": 3.0,
        "min_interval_ms": 500,
        "cooldown_on_429_s": 130,
    },
    "expired_historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "admin": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 130,
    },
}

UPSTOX_RATE_LIMITS: dict[str, dict[str, float | tuple[tuple[int, float], ...]]] = {
    "orders": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 60,
        "extra_windows": ((500, 60.0), (2000, 1800.0)),
    },
    "quotes": {
        "sustained_rps": 25.0,
        "burst_rps": 50.0,
        "min_interval_ms": 40,
        "cooldown_on_429_s": 60,
    },
    "historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "option_chain": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "funds": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "positions": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "holdings": {
        "sustained_rps": 2.0,
        "burst_rps": 5.0,
        "min_interval_ms": 500,
        "cooldown_on_429_s": 60,
    },
    "options_historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "expired_historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "admin": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 60,
    },
}

PAPER_RATE_LIMITS: dict[str, dict[str, float]] = {
    "orders": {"sustained_rps": 1000.0, "burst_rps": 1000.0, "min_interval_ms": 0, "cooldown_on_429_s": 0},
    "quotes": {"sustained_rps": 1000.0, "burst_rps": 1000.0, "min_interval_ms": 0, "cooldown_on_429_s": 0},
    "historical": {"sustained_rps": 1000.0, "burst_rps": 1000.0, "min_interval_ms": 0, "cooldown_on_429_s": 0},
    "admin": {"sustained_rps": 1000.0, "burst_rps": 1000.0, "min_interval_ms": 0, "cooldown_on_429_s": 0},
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
    """Token bucket with min_interval enforcement and 429 cooldown support."""

    def __init__(
        self,
        config: RateLimitConfig | _BucketConfig | None = None,
        restore_cooldown: float = 60.0,
        min_interval_ms: float = 0,
        cooldown_on_429_s: float = 60.0,
    ) -> None:
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
        self._restore_cooldown = restore_cooldown
        # G7 extensions: min_interval between requests, cooldown on 429
        self._min_interval_s = min_interval_ms / 1000.0
        self._last_request_time: float = 0.0
        self._cooldown_until: float = 0.0
        self._cooldown_on_429_s = cooldown_on_429_s

    @property
    def rate(self) -> float:
        return self.config.rate_per_second

    @rate.setter
    def rate(self, value: float) -> None:
        with self._lock:
            if self._original_rate is None:
                self._original_rate = self.config.rate_per_second
            self.config.rate_per_second = value
            self._reduced_at = time.monotonic()

    def _maybe_restore_rate(self) -> None:
        """Restore original rate if cooldown has elapsed."""
        if self._reduced_at is None or self._original_rate is None:
            return
        elapsed = time.monotonic() - self._reduced_at
        if elapsed >= self._restore_cooldown:
            with self._lock:
                self.config.rate_per_second = self._original_rate
                self._reduced_at = None
                self._original_rate = None

    def _check_cooldown(self) -> None:
        """If in 429 cooldown, sleep until it expires."""
        now = time.monotonic()
        if now < self._cooldown_until:
            sleep_time = self._cooldown_until - now
            time.sleep(sleep_time)

    def _check_min_interval(self) -> None:
        """Enforce minimum interval between requests."""
        if self._min_interval_s <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval_s:
            sleep_time = self._min_interval_s - elapsed
            time.sleep(sleep_time)

    def trigger_cooldown(self) -> None:
        """Trigger cooldown after receiving HTTP 429."""
        self._cooldown_until = time.monotonic() + self._cooldown_on_429_s
        self.reduce_rate(0.5)

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        self._maybe_restore_rate()
        self._check_cooldown()
        self._check_min_interval()
        if tokens > self._capacity:
            return False
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._last_request_time = time.monotonic()
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

    def reduce_rate(self, factor: float) -> None:
        """Reduce rate by factor (e.g. 0.5 = halve)."""
        self.rate = self.rate * factor


class RollingWindowCounter:
    """Rolling-window rate counter for extra_windows enforcement.

    Tracks request timestamps and enforces caps like "250/min" or "7000/day".
    Thread-safe via internal lock.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window_s = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, timeout: float | None = None) -> bool:
        """Wait until a request slot is available within the rolling window."""
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            with self._lock:
                self._prune()
                if len(self._timestamps) < self._max:
                    self._timestamps.append(time.monotonic())
                    return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _prune(self) -> None:
        """Remove timestamps older than the window."""
        cutoff = time.monotonic() - self._window_s
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()


class MultiBucketRateLimiter:
    """Multi-bucket rate limiter with optional rolling-window enforcement."""

    def __init__(
        self,
        configs: dict[str, RateLimitConfig | _BucketConfig],
        extra_windows: dict[str, list[tuple[int, float]]] | None = None,
    ) -> None:
        self._buckets: dict[str, TokenBucketRateLimiter] = {}
        for k, v in configs.items():
            self._buckets[k] = TokenBucketRateLimiter(v)
        self._categories = tuple(configs.keys())
        # Rolling-window counters for extra_windows (e.g. 250/min, 7000/day)
        self._rolling: dict[str, list[RollingWindowCounter]] = {}
        if extra_windows:
            for bucket, windows in extra_windows.items():
                self._rolling[bucket] = [
                    RollingWindowCounter(max_req, window_s)
                    for max_req, window_s in windows
                ]

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
        # Check rolling windows first (if any)
        rolling_counters = self._rolling.get(category)
        if rolling_counters:
            for counter in rolling_counters:
                if not counter.acquire(timeout=timeout):
                    return False
        return self._resolve(category).acquire(tokens, timeout)

    def reduce_rate(self, category: str, factor: float) -> None:
        bucket = self.get_bucket(category) if category in self._buckets else self._resolve(category)
        bucket.reduce_rate(factor)

    def trigger_cooldown(self, category: str) -> None:
        """Trigger 429 cooldown for a specific bucket."""
        bucket = self.get_bucket(category) if category in self._buckets else self._resolve(category)
        bucket.trigger_cooldown()


def limiter_from_table(
    table: Mapping[str, Mapping[str, float | tuple[tuple[int, float], ...]]],
) -> MultiBucketRateLimiter:
    """Build MultiBucketRateLimiter from a rate-limit table with extended fields."""
    configs: dict[str, _BucketConfig] = {}
    extra_windows: dict[str, list[tuple[int, float]]] = {}
    for name, row in table.items():
        configs[name] = _BucketConfig(
            rate_per_second=float(row["sustained_rps"]),
            capacity=int(row["burst_rps"]),
        )
        # Parse extra_windows if present
        extra_raw = row.get("extra_windows")
        if extra_raw and isinstance(extra_raw, tuple):
            extra_windows[name] = list(extra_raw)
    # Create limiter with extra_windows
    limiter = MultiBucketRateLimiter(configs, extra_windows=extra_windows if extra_windows else None)
    # Apply min_interval_ms and cooldown_on_429_s to each bucket
    for name, row in table.items():
        bucket = limiter._buckets.get(name)
        if bucket:
            min_interval_ms = float(row.get("min_interval_ms", 0))
            cooldown_s = float(row.get("cooldown_on_429_s", 60.0))
            bucket._min_interval_s = min_interval_ms / 1000.0
            bucket._cooldown_on_429_s = cooldown_s
    return limiter


_TABLES_BY_BROKER: dict[str, Mapping[str, Mapping[str, float | tuple[tuple[int, float], ...]]]] = {
    "dhan": DHAN_RATE_LIMITS,
    "upstox": UPSTOX_RATE_LIMITS,
    "paper": PAPER_RATE_LIMITS,
}


def limiter_from_profile(broker_id: str, profile: object | None) -> MultiBucketRateLimiter:
    """Build a MultiBucketRateLimiter from the broker table, overridden by profile.

    The bucket topology (rates, capacities, extra rolling windows) comes from
    the existing per-broker table; the ``RateLimitProfile`` supplies:

    - ``cooldown_on_429_s`` — 429 cooldown AND rate-restore cooldown for every
      bucket (replaces the hardcoded 60s restore default).
    - ``min_interval_ms`` — optional mapping of bucket name -> ms; applied as
      ``min_interval_ms / 1000.0`` to matching buckets.

    Falls back to the table constants when ``profile`` is None or lacks fields.
    """
    table = _TABLES_BY_BROKER.get((broker_id or "paper").lower().strip(), PAPER_RATE_LIMITS)
    limiter = limiter_from_table(table)
    if profile is None:
        return limiter

    cooldown = getattr(profile, "cooldown_on_429_s", None)
    if cooldown is not None:
        for bucket in limiter._buckets.values():
            bucket._cooldown_on_429_s = float(cooldown)
            bucket._restore_cooldown = float(cooldown)

    min_intervals = getattr(profile, "min_interval_ms", None)
    if min_intervals:
        for name, ms in dict(min_intervals).items():
            bucket = limiter._buckets.get(name)
            if bucket is not None:
                bucket._min_interval_s = float(ms) / 1000.0
    return limiter
