"""Rate limiting with token bucket algorithm — thread-safe, burst-aware.

This is the CANONICAL rate limiter for the whole system. Per-broker copies
were removed (board Decision #4); brokers now obtain their limiter through
:func:`create_rate_limiter`, which builds buckets from the broker's
``RateLimitProfile`` definitions in ``domain.capabilities.broker_capabilities``.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limiter bucket."""

    rate_per_second: float = 10.0
    capacity: int = 10

    def __post_init__(self):
        if self.rate_per_second <= 0:
            raise ValueError(f"rate_per_second must be positive, got {self.rate_per_second}")
        if self.capacity <= 0:
            raise ValueError(f"capacity must be positive, got {self.capacity}")


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Tokens are refilled at ``rate_per_second`` and burst up to ``capacity``.
    Use ``acquire()`` to block until a token is available.

    Inspired by Trade_J's TokenBucketRateLimiter with ReentrantLock.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._tokens: float = float(self.config.capacity)
        self._last_refill_nanos: float = time.monotonic_ns()
        self._capacity: float = float(self.config.capacity)
        self._lock = threading.Lock()
        self._original_rate: float | None = None
        self._reduced_at: float | None = None

    @property
    def available_tokens(self) -> float:
        with self._lock:
            # Read-only estimation — does NOT mutate state
            now_ns = time.monotonic_ns()
            elapsed_sec = (now_ns - self._last_refill_nanos) / 1_000_000_000.0
            estimated = self._tokens + (elapsed_sec * self.config.rate_per_second)
            return min(self._capacity, estimated)

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
        """Acquire ``tokens`` from the bucket.

        Args:
            tokens: Number of tokens to consume.
            timeout: Maximum time to wait in seconds. ``None`` blocks forever.

        Returns:
            ``True`` if tokens were acquired, ``False`` if timeout reached.
        """
        if tokens > self._capacity:
            return False

        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

            # Not enough tokens — wait or timeout
            if deadline is not None and time.monotonic() >= deadline:
                return False

            # Sleep for a fraction of the refill time
            sleep_time = min(
                timeout if timeout is not None else 0.001,
                1.0 / self.config.rate_per_second if self.config.rate_per_second > 0 else 0.001,
            )
            sleep_time = max(sleep_time, 0.001)
            time.sleep(sleep_time)

    async def acquire_async(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """Async variant of ``acquire`` that never blocks the event loop."""
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
            sleep_time = max(sleep_time, 0.001)
            await asyncio.sleep(sleep_time)

    def reset(self) -> None:
        """Reset the bucket to full capacity."""
        with self._lock:
            self._tokens = float(self.config.capacity)
            self._last_refill_nanos = time.monotonic_ns()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now_ns = time.monotonic_ns()
        elapsed_sec = (now_ns - self._last_refill_nanos) / 1_000_000_000.0
        if elapsed_sec > 0:
            new_tokens = elapsed_sec * self.config.rate_per_second
            self._tokens = min(self._capacity, self._tokens + new_tokens)
            self._last_refill_nanos = now_ns

    def __repr__(self) -> str:
        return (
            f"TokenBucketRateLimiter(rate={self.config.rate_per_second}, "
            f"capacity={self.config.capacity}, "
            f"available={self._tokens:.1f})"
        )


class MultiBucketRateLimiter:
    """Manages multiple rate limit buckets by category (e.g. orders, quotes, data).

    Maps 1:1 to Trade_J's MultiBucketRateLimiter pattern.
    """

    def __init__(self, configs: dict[str, RateLimitConfig]):
        self._buckets: dict[str, TokenBucketRateLimiter] = {}
        for category, config in configs.items():
            self._buckets[category] = TokenBucketRateLimiter(config)
        self._categories = tuple(configs.keys())

    def _resolve_bucket(self, category: str) -> TokenBucketRateLimiter:
        """Resolve a bucket, falling back to ``admin`` then any known bucket."""
        bucket = self._buckets.get(category)
        if bucket is not None:
            return bucket
        fallback = self._buckets.get("admin")
        if fallback is not None:
            logger.warning(
                "rate_limit_unknown_category_fallback",
                extra={"requested": category, "fallback": "admin"},
            )
            return fallback
        if self._buckets:
            name = next(iter(self._buckets))
            logger.warning(
                "rate_limit_unknown_category_fallback",
                extra={"requested": category, "fallback": name},
            )
            return self._buckets[name]
        raise ValueError(f"Unknown category: {category}")

    def record_api_rate_limit(self, broker: str = "unknown") -> None:
        """Record a trading/data API rate-limit event (not TOTP/login)."""
        try:
            from infrastructure.auth.metrics import AuthMetrics

            AuthMetrics.api_rate_limit(broker)
        except Exception:
            pass

    def acquire(self, category: str, tokens: int = 1, timeout: float | None = None) -> bool:
        """Acquire tokens for a given category bucket."""
        return self._resolve_bucket(category).acquire(tokens, timeout)

    async def acquire_async(
        self,
        category: str,
        tokens: int = 1,
        timeout: float | None = None,
    ) -> bool:
        """Acquire tokens for a given category bucket without blocking the event loop."""
        return await self._resolve_bucket(category).acquire_async(tokens, timeout)

    def categories(self) -> list[str]:
        """Return a list of all category names."""
        return list(self._categories)

    def get_bucket(self, category: str) -> TokenBucketRateLimiter:
        """Get the underlying bucket for inspection."""
        bucket = self._buckets.get(category)
        if bucket is None:
            raise ValueError(f"Unknown category: {category}")
        return bucket

    def reduce_rate(self, category: str, factor: float) -> None:
        """Reduce the rate for a category (e.g., after 429 response)."""
        bucket = self.get_bucket(category)
        bucket.rate = bucket.rate * factor
        bucket._reduced_at = time.monotonic()

    def increase_rate(self, category: str, factor: float) -> None:
        """Increase the rate for a category."""
        bucket = self.get_bucket(category)
        bucket.rate = bucket.rate * factor

    def maybe_recover_rate(self, category: str, recovery_seconds: float = 300.0) -> None:
        """Auto-recover rate after recovery_seconds if no new reductions occurred."""
        bucket = self.get_bucket(category)
        if (
            hasattr(bucket, "_reduced_at")
            and bucket._reduced_at is not None
            and bucket._original_rate is not None
            and (time.monotonic() - bucket._reduced_at) > recovery_seconds
        ):
            bucket.rate = bucket._original_rate
            bucket._reduced_at = None
            bucket._original_rate = None


class EndpointRateLimiter:
    """Per-endpoint rate limiter with blocking acquire.

    Wraps MultiBucketRateLimiter to provide a simple per-endpoint
    interface compatible with broker adapters that track rate limits
    per URL endpoint.

    Usage::

        limiter = EndpointRateLimiter(rate_per_second=10.0)
        limiter.register("/market-quote/RELIANCE")  # pre-register
        limiter.acquire("/market-quote/RELIANCE")   # blocks until allowed
    """

    def __init__(self, rate_per_second: float = 10.0, capacity: int = 10):
        config = RateLimitConfig(rate_per_second=rate_per_second, capacity=capacity)
        self._multi = MultiBucketRateLimiter({"_default": config})
        self._rate_per_second = rate_per_second
        self._capacity = capacity
        self._lock = threading.Lock()

    def register(self, endpoint: str) -> None:
        """Pre-register an endpoint bucket for predictable rate limiting."""
        with self._lock:
            if endpoint not in self._multi._buckets:
                config = RateLimitConfig(
                    rate_per_second=self._rate_per_second,
                    capacity=self._capacity,
                )
                self._multi._buckets[endpoint] = TokenBucketRateLimiter(config)

    def acquire(self, endpoint: str = "default", timeout: float | None = None) -> None:
        """Block until a request to the given endpoint is allowed.

        Args:
            endpoint: Endpoint identifier for per-endpoint tracking.
            timeout: Maximum wait time in seconds. None blocks forever.
        """
        with self._lock:
            if endpoint not in self._multi._buckets:
                config = RateLimitConfig(
                    rate_per_second=self._rate_per_second,
                    capacity=self._capacity,
                )
                self._multi._buckets[endpoint] = TokenBucketRateLimiter(config)
        self._multi.acquire(endpoint, tokens=1, timeout=timeout)

    @property
    def rate(self) -> float:
        return self._rate_per_second

    @rate.setter
    def rate(self, value: float) -> None:
        self._rate_per_second = value
        for bucket in self._multi._buckets.values():
            bucket.rate = value


# ---------------------------------------------------------------------------
# Broker-config-driven factory
# ---------------------------------------------------------------------------

# Maps a broker id to the function returning its BrokerCapabilities. Each
# broker's rate_limit_profiles (RateLimitProfile in domain.capabilities.broker_capabilities)
# are the canonical source of per-broker RPS / capacity values.
_BROKER_CAPABILITIES: dict[str, Callable[[], Any]] = {}


def _register_broker_capabilities(broker_id: str, fn: Callable[[], Any]) -> None:
    """Register the capability loader used by :func:`create_rate_limiter`."""
    _BROKER_CAPABILITIES[broker_id] = fn


def _default_capabilities_loader(broker_id: str) -> Any | None:
    """Return a broker's capabilities via capability declaration, never by name.

    Dispatch order (all capability-driven, no broker-name equality branch):

    1. Explicit registration hook — brokers may call
       :func:`_register_broker_capabilities` (e.g. at import time) to declare
       their loader. This is the preferred, fully broker-agnostic path.
    2. The broker's ``BrokerPlugin`` declares *where* its capabilities live via
       the ``capabilities_module`` / ``capabilities_fn`` metadata strings. The
       resilience layer imports that module by name and calls the declared
       factory — no concrete broker names are hard-coded here (DR-B3).
    3. Otherwise warn and return ``None`` so callers fall back to default
       buckets rather than inventing per-broker behavior.
    """
    if broker_id in _BROKER_CAPABILITIES:
        return _BROKER_CAPABILITIES[broker_id]()

    # Capability-flag dispatch: the broker declares its capabilities loader in
    # its BrokerPlugin metadata. No hard-coded broker names here.
    from infrastructure.broker_plugin import get_broker_plugin

    plugin = get_broker_plugin(broker_id)
    if plugin is not None and plugin.capabilities_module and plugin.capabilities_fn:
        try:
            _mod = importlib.import_module(plugin.capabilities_module)
            return getattr(_mod, plugin.capabilities_fn)()
        except Exception as exc:
            logger.warning(
                "capabilities_load_failed",
                extra={"broker_id": broker_id, "error": str(exc)},
            )
            return None

    logger.warning(
        "no_capabilities_loader_registered",
        extra={"broker_id": broker_id},
    )
    return None


_DEFAULT_BUCKET_CAPACITY = 30


def create_rate_limiter(
    broker_id: str = "dhan",
    caps: Any | None = None,
) -> MultiBucketRateLimiter:
    """Create a :class:`MultiBucketRateLimiter` from a broker's profiles.

    The RPS / capacity values come from the broker's ``RateLimitProfile``
    entries (``rate_per_second`` -> profile.sustained_rps,
    ``capacity`` -> profile.burst_rps or 2x sustained when unset).

    Args:
        broker_id: broker id resolved via capability metadata (extensible).
        caps: Optional pre-built ``BrokerCapabilities`` (or any object with
            ``rate_limit_profiles``). When omitted, the capabilities are
            resolved via :func:`register_capabilities_loader` (the broker
            registers its loader at import time). Callers in a broker
            package should pass their own ``dhan_capabilities()`` /
            ``upstox_capabilities()`` directly so ``brokers.common`` stays
            broker-agnostic.

    Returns:
        A configured ``MultiBucketRateLimiter`` keyed by endpoint class.
    """
    if caps is None:
        caps = _default_capabilities_loader(broker_id)
    if caps is None or not getattr(caps, "rate_limit_profiles", None):
        logger.warning(
            "no_rate_limit_profiles",
            extra={"broker_id": broker_id, "defaulting_to": "admin"},
        )
        return MultiBucketRateLimiter(
            {"admin": RateLimitConfig(rate_per_second=10.0, capacity=_DEFAULT_BUCKET_CAPACITY)}
        )

    configs: dict[str, RateLimitConfig] = {}
    for profile in caps.rate_limit_profiles:
        rate = float(profile.sustained_rps)
        capacity = int(profile.burst_rps) if profile.burst_rps else int(rate * 2)
        configs[profile.endpoint_class] = RateLimitConfig(
            rate_per_second=rate, capacity=max(capacity, 1)
        )

    # Catch-all for uncategorized admin/account endpoints (profile, login, …).
    # HTTP clients map unknown paths to "admin"; without this bucket they either
    # hard-fail (Upstox) or silently skip limiting (Dhan ValueError bypass).
    if "admin" not in configs:
        configs["admin"] = RateLimitConfig(
            rate_per_second=10.0, capacity=_DEFAULT_BUCKET_CAPACITY
        )

    # Legacy aliases used by older Dhan bucket maps / Upstox "data" key.
    if "market_data" not in configs and "quotes" in configs:
        configs["market_data"] = configs["quotes"]
    if "data" not in configs and "historical" in configs:
        configs["data"] = configs["historical"]

    return MultiBucketRateLimiter(configs)


class DhanRateLimiterMetrics:
    """Collects rate limiter metrics for observability (Dhan + generic).

    Tracks:
      - Request timestamps per category (for requests/sec calculation)
      - Queue depth (waiting acquire calls)
      - Rate limit rejections (timeouts)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._request_timestamps: dict[str, list[float]] = {}
        self._queue_depth: dict[str, int] = {}
        self._rejections: dict[str, int] = {}

    def record_request(self, category: str) -> None:
        """Record a successful rate limit acquisition."""
        with self._lock:
            timestamps = self._request_timestamps.setdefault(category, [])
            # Keep only last 60 seconds of data
            cutoff = time.monotonic() - 60.0
            timestamps[:] = [t for t in timestamps if t > cutoff]
            timestamps.append(time.monotonic())

    def record_rejection(self, category: str) -> None:
        """Record a rate limit rejection (timeout)."""
        with self._lock:
            self._rejections[category] = self._rejections.get(category, 0) + 1

    def increment_queue_depth(self, category: str) -> None:
        """Increment queue depth for a category."""
        with self._lock:
            self._queue_depth[category] = self._queue_depth.get(category, 0) + 1

    def decrement_queue_depth(self, category: str) -> None:
        """Decrement queue depth for a category."""
        with self._lock:
            depth = self._queue_depth.get(category, 0)
            if depth > 0:
                self._queue_depth[category] = depth - 1

    def get_requests_per_second(self, category: str) -> float:
        """Get current request rate for a category (last 10 seconds)."""
        with self._lock:
            timestamps = self._request_timestamps.get(category, [])
            if not timestamps:
                return 0.0
            cutoff = time.monotonic() - 10.0
            recent = [t for t in timestamps if t > cutoff]
            if len(recent) < 2:
                return float(len(recent))
            duration = recent[-1] - recent[0]
            if duration <= 0:
                return float(len(recent))
            return (len(recent) - 1) / duration

    def get_queue_depth(self, category: str) -> int:
        """Get current queue depth for a category."""
        with self._lock:
            return self._queue_depth.get(category, 0)

    def get_rejections(self, category: str) -> int:
        """Get total rejections for a category."""
        with self._lock:
            return self._rejections.get(category, 0)

    def snapshot(self) -> dict[str, Any]:
        """Get a full metrics snapshot for all categories."""
        with self._lock:
            all_categories = set(self._request_timestamps.keys()) | set(self._queue_depth.keys())
            result = {}
            for cat in all_categories:
                result[cat] = {
                    "requests_per_second": self._calc_rps_unsafe(cat),
                    "queue_depth": self._queue_depth.get(cat, 0),
                    "rejections": self._rejections.get(cat, 0),
                }
            return result

    def _calc_rps_unsafe(self, category: str) -> float:
        """Calculate RPS without acquiring lock (caller must hold lock)."""
        timestamps = self._request_timestamps.get(category, [])
        if not timestamps:
            return 0.0
        cutoff = time.monotonic() - 10.0
        recent = [t for t in timestamps if t > cutoff]
        if len(recent) < 2:
            return float(len(recent))
        duration = recent[-1] - recent[0]
        if duration <= 0:
            return float(len(recent))
        return (len(recent) - 1) / duration
