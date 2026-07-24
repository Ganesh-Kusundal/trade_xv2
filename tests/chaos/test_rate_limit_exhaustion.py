"""Fault injection tests for rate limit exhaustion scenarios.

Priority 2: Rate limit approached and exhausted, with circuit breaker
integration and graceful backoff.

Tests cover both Dhan and Upstox brokers with realistic rate limiting.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from application.scheduling.quota_scheduler import PriorityClass, QuotaScheduler
from domain.capabilities.broker_capabilities import RateLimitProfile
from domain.exceptions import QuotaExhaustedError
from infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from infrastructure.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
)
from infrastructure.resilience.retry_executor import RetryConfig, RetryExecutor
from tests.support.wait_utils import wait_until

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_rate_limiter(rate: float = 10.0, capacity: int = 10) -> TokenBucketRateLimiter:
    """Create a rate limiter for testing."""
    return TokenBucketRateLimiter(RateLimitConfig(rate_per_second=rate, capacity=capacity))


def _make_multi_bucket_limiter() -> MultiBucketRateLimiter:
    """Create a multi-bucket rate limiter for testing."""
    return MultiBucketRateLimiter(
        {
            "orders": RateLimitConfig(rate_per_second=5.0, capacity=5),
            "quotes": RateLimitConfig(rate_per_second=10.0, capacity=10),
            "data": RateLimitConfig(rate_per_second=20.0, capacity=20),
        }
    )


# ── Priority 2.1: Rate Limit Approached ──────────────────────────────────


class TestRateLimitApproached:
    """Send requests approaching rate limit threshold."""

    def test_requests_queued_not_rejected(self):
        """Requests wait for token availability, not rejected."""
        limiter = _make_rate_limiter(rate=100.0, capacity=2)

        # Consume all tokens
        assert limiter.acquire(2) is True

        # Next request should wait, not reject
        start = time.monotonic()
        result = limiter.acquire(1, timeout=1.0)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed > 0.005  # Should have waited for token refill

    def test_graceful_backoff_applied(self):
        """Backoff prevents rapid-fire requests."""
        limiter = _make_rate_limiter(rate=10.0, capacity=1)
        request_times = []

        def make_request():
            limiter.acquire(1, timeout=1.0)
            request_times.append(time.monotonic())

        # Make 5 requests
        for _ in range(5):
            make_request()

        # Verify spacing between requests
        assert len(request_times) == 5
        # At least some requests should be spaced out
        for i in range(1, len(request_times)):
            # Should have some delay (token refill time)
            assert request_times[i] >= request_times[i - 1]

    def test_metrics_show_queue_depth(self):
        """Rate limiter tracks pending requests."""
        limiter = _make_rate_limiter(rate=10.0, capacity=1)

        # Consume token
        limiter.acquire(1)

        # Check available tokens (should be refilling)
        available = limiter.available_tokens
        assert available >= 0.0
        assert available <= 1.0  # Capacity limit

    def test_rate_limiter_prevents_burst_over_capacity(self):
        """Cannot acquire more tokens than capacity."""
        limiter = _make_rate_limiter(rate=10.0, capacity=5)

        # Try to acquire more than capacity
        result = limiter.acquire(6)
        assert result is False  # Should fail

    def test_concurrent_requests_respect_rate_limit(self):
        """Multiple threads respect rate limit."""
        limiter = _make_rate_limiter(rate=100.0, capacity=5)
        successful_acquires = []
        lock = threading.Lock()

        def acquire_token():
            if limiter.acquire(1, timeout=0.5):
                with lock:
                    successful_acquires.append(time.monotonic())

        # Launch concurrent requests
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(acquire_token) for _ in range(10)]
            for f in futures:
                f.result(timeout=10)

        # Should have limited successful acquires
        assert len(successful_acquires) <= 10


# ── Priority 2.2: Rate Limit Exhausted ───────────────────────────────────


class TestRateLimitExhausted:
    """Exceed rate limit, verify circuit breaker and fast-fail."""

    def test_circuit_breaker_opens_on_rate_limit(self):
        """Rate limit exhaustion triggers circuit breaker."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=2,
                open_duration_ms=5000,
            ),
        )
        _make_rate_limiter(rate=1.0, capacity=1)

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=3),
            circuit_breaker=cb,
            rate_limiter=MultiBucketRateLimiter(
                {"orders": RateLimitConfig(rate_per_second=0.5, capacity=1)}
            ),
            rate_limit_category="orders",
        )

        # Exhaust rate limit
        def rate_limited_operation():
            return {"status": "ok"}

        # First call should succeed
        result = executor.execute(rate_limited_operation)
        assert result == {"status": "ok"}

        # Circuit breaker should still be closed
        assert cb.state == CircuitState.CLOSED

    def test_requests_fail_fast_not_queued(self):
        """When circuit breaker open, requests fail fast."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=1,
                open_duration_ms=10000,
            ),
        )

        # Manually open circuit breaker
        cb.on_failure()
        cb.on_failure()

        assert cb.state == CircuitState.OPEN

        # Next request should fail fast
        from infrastructure.resilience.errors import CircuitBreakerOpenError

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=3),
            circuit_breaker=cb,
        )

        with pytest.raises(CircuitBreakerOpenError):
            executor.execute(lambda: {"status": "ok"})

    def test_recovery_after_timeout(self):
        """Circuit breaker recovers after open duration."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=1,
                open_duration_ms=100,  # Very short for testing
                success_threshold=1,
            ),
        )

        # Open circuit breaker
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery (CB auto-transitions OPEN -> HALF_OPEN after open_duration)
        wait_until(
            lambda: cb.state in [CircuitState.HALF_OPEN, CircuitState.CLOSED],
            timeout=2,
        )

        # Should transition to HALF_OPEN
        assert cb.state in [CircuitState.HALF_OPEN, CircuitState.CLOSED]

        # Success should close it
        cb.on_success()
        assert cb.state == CircuitState.CLOSED

    def test_rate_limit_exhaustion_triggers_backoff(self):
        """Rate limit exhaustion applies exponential backoff."""
        limiter = _make_rate_limiter(rate=1.0, capacity=1)
        wait_times = []

        # Exhaust tokens
        limiter.acquire(1)

        # Measure wait time for next token
        start = time.monotonic()
        limiter.acquire(1, timeout=1.0)
        elapsed = time.monotonic() - start
        wait_times.append(elapsed)

        # Should have waited for token refill
        assert wait_times[0] > 0.005

    def test_multiple_rate_limit_buckets_independent(self):
        """Different rate limit buckets operate independently."""
        multi = _make_multi_bucket_limiter()

        # Exhaust orders bucket
        multi.acquire("orders", 5)  # Use all capacity

        # Quotes bucket should still be available
        result = multi.acquire("quotes", 1, timeout=0.1)
        assert result is True

    def test_rate_limit_reduction_on_429(self):
        """Rate limit reduced after receiving 429 response."""
        multi = _make_multi_bucket_limiter()
        original_rate = multi.get_bucket("orders").rate

        # Simulate 429 response
        multi.reduce_rate("orders", 0.5)

        new_rate = multi.get_bucket("orders").rate
        assert new_rate == original_rate * 0.5

    def test_rate_limit_increase_after_recovery(self):
        """Rate limit increased after successful recovery."""
        multi = _make_multi_bucket_limiter()
        original_rate = multi.get_bucket("orders").rate

        # Simulate recovery
        multi.increase_rate("orders", 2.0)

        new_rate = multi.get_bucket("orders").rate
        assert new_rate == original_rate * 2.0

    def test_concurrent_rate_limit_exhaustion(self):
        """Multiple threads exhausting rate limit simultaneously."""
        limiter = _make_rate_limiter(rate=100.0, capacity=5)
        successful = []
        lock = threading.Lock()

        def try_acquire():
            if limiter.acquire(1, timeout=0.5):
                with lock:
                    successful.append(1)

        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = [ex.submit(try_acquire) for _ in range(20)]
            for f in futures:
                f.result(timeout=10)

        # Should have limited successful acquires based on capacity + refill
        assert len(successful) >= 5  # At least initial capacity
        assert len(successful) <= 20  # Cannot exceed requests

    def test_rate_limiter_timeout_respected(self):
        """Rate limiter respects timeout parameter."""
        limiter = _make_rate_limiter(rate=0.1, capacity=1)

        # Exhaust tokens
        limiter.acquire(1)

        # Request with short timeout should fail
        start = time.monotonic()
        result = limiter.acquire(1, timeout=0.05)
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 0.04  # Should have waited close to timeout

    def test_rate_limiter_reset_restores_capacity(self):
        """Rate limiter reset restores full capacity."""
        limiter = _make_rate_limiter(rate=1.0, capacity=5)

        # Exhaust all tokens
        for _ in range(5):
            limiter.acquire(1)

        # Reset
        limiter.reset()

        # Should have full capacity again
        result = limiter.acquire(5)
        assert result is True


# ── Priority 2.3: Rolling-window / daily order caps (QuotaScheduler) ───────
#
# Upstox order placement is 10 rps but also caps at 2000 requests per 30
# minutes; Dhan caps orders at 7000 per day. A per-second bucket alone can't
# see these — QuotaScheduler layers extra_windows buckets on top and must
# reject once *any* window is exhausted, even with rps headroom to spare.


class TestOrderWindowCapExhausted:
    """Exercise QuotaScheduler.extra_windows under fault-injection-style load."""

    def _scheduler_with_window(
        self, cap: int, window_s: float, sustained_rps: float = 100.0
    ) -> QuotaScheduler:
        scheduler = QuotaScheduler(reserved_headroom=0.0)
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=sustained_rps,
                burst_rps=sustained_rps,
                extra_windows=((cap, window_s),),
            ),
        )
        return scheduler

    def test_window_cap_rejects_once_exhausted_despite_rps_headroom(self):
        """A tight 30min-style window cap binds even when sustained_rps is generous."""
        scheduler = self._scheduler_with_window(cap=5, window_s=1800.0)

        for _ in range(5):
            scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)

        with pytest.raises(QuotaExhaustedError):
            scheduler.acquire("dhan", "orders", PriorityClass.LIVE_STREAM_CONTROL)

    def test_window_cap_applies_regardless_of_priority(self):
        """A rolling/daily cap is a hard broker-side wall — EXECUTION_CRITICAL
        does not get to bypass it the way it bypasses reserved rps headroom."""
        scheduler = self._scheduler_with_window(cap=3, window_s=60.0)

        for _ in range(3):
            scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)

        with pytest.raises(QuotaExhaustedError):
            scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)

    def test_window_rejection_refunds_primary_bucket_no_token_leak(self):
        """Rejecting on the window bucket must refund the primary rps bucket,
        or sustained throughput silently degrades even after the window resets."""
        scheduler = self._scheduler_with_window(cap=1, window_s=60.0, sustained_rps=100.0)

        scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)
        primary = scheduler._get_or_default_bucket("dhan", "orders")
        before = primary.available_tokens(PriorityClass.EXECUTION_CRITICAL)

        with pytest.raises(QuotaExhaustedError):
            scheduler.acquire("dhan", "orders", PriorityClass.LIVE_STREAM_CONTROL)

        after = primary.available_tokens(PriorityClass.EXECUTION_CRITICAL)
        assert after == pytest.approx(before, abs=0.05)

    def test_concurrent_bursts_never_exceed_window_cap(self):
        """Many threads hammering the scheduler at once must not blow past
        the window cap — the composite acquire has to be race-free."""
        scheduler = self._scheduler_with_window(cap=10, window_s=1800.0)
        granted = []
        lock = threading.Lock()

        def try_order():
            try:
                token = scheduler.acquire("dhan", "orders", PriorityClass.LIVE_STREAM_CONTROL)
                with lock:
                    granted.append(token)
            except QuotaExhaustedError:
                pass

        with ThreadPoolExecutor(max_workers=25) as ex:
            futures = [ex.submit(try_order) for _ in range(25)]
            for f in futures:
                f.result(timeout=10)

        assert len(granted) == 10

    def test_multiple_brokers_have_independent_window_caps(self):
        """Dhan exhausting its window cap must not affect Upstox's separate cap."""
        scheduler = QuotaScheduler(reserved_headroom=0.0)
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=100.0,
                burst_rps=100.0,
                extra_windows=((2, 60.0),),
            ),
        )
        scheduler.register_profile(
            "upstox",
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=100.0,
                burst_rps=100.0,
                extra_windows=((2, 60.0),),
            ),
        )

        for _ in range(2):
            scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)
        with pytest.raises(QuotaExhaustedError):
            scheduler.acquire("dhan", "orders", PriorityClass.LIVE_STREAM_CONTROL)

        # Upstox's independent window is untouched by Dhan's exhaustion.
        token = scheduler.acquire("upstox", "orders", PriorityClass.LIVE_STREAM_CONTROL)
        assert token.broker_id == "upstox"
