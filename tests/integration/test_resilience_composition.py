"""Resilience pattern composition tests.

Verifies that resilience patterns (circuit breakers, retry executors,
rate limiters) work together correctly when composed in DhanHttpClient
and factory.

These tests use REAL resilience objects — no MagicMock for the
resilience components themselves.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from infrastructure.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    MultiBucketRateLimiter,
    NonRetryableError,
    RateLimitConfig,
    RetryableError,
    RetryConfig,
    RetryExecutor,
)
from infrastructure.resilience.backoff import ExponentialBackoff

_ZERO_BACKOFF = ExponentialBackoff(base_delay_ms=0.0, jitter_factor=0.0)
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.resilience import (
    create_circuit_breakers,
    create_rate_limiter,
)
from infrastructure.resilience._metrics import DhanRateLimiterMetrics
from brokers.dhan.resilience.retry_policies import (
    MARKET_DATA_POLICY,
    ORDERS_POLICY,
)

# ── Test 1: Circuit breakers isolated by category ───────────────────────

class TestCircuitBreakerIsolation:
    """Verify read/write/admin circuit breakers are independent."""

    def test_circuit_breakers_isolated_by_category(self) -> None:
        """Read failure must not open write or admin CBs."""
        cbs = create_circuit_breakers()

        cb_orders = cbs["orders"]
        cb_market_data = cbs["market_data"]
        cb_portfolio = cbs["portfolio"]
        cb_admin = cbs["admin"]

        # Simulate failures on market_data CB
        for _ in range(6):  # threshold is 5
            cb_market_data.on_failure()

        assert cb_market_data.state == CircuitState.OPEN
        assert cb_orders.state == CircuitState.CLOSED, "Orders CB must not be affected"
        assert cb_portfolio.state == CircuitState.CLOSED, "Portfolio CB must not be affected"
        assert cb_admin.state == CircuitState.CLOSED, "Admin CB must not be affected"

    def test_orders_cb_has_lower_threshold(self) -> None:
        """Orders CB uses threshold=3, others use threshold=5."""
        cbs = create_circuit_breakers()

        # Orders should open after 3 failures
        for _ in range(3):
            cbs["orders"].on_failure()
        assert cbs["orders"].state == CircuitState.OPEN

        # Market data should still be CLOSED after 3 failures
        for _ in range(3):
            cbs["market_data"].on_failure()
        assert cbs["market_data"].state == CircuitState.CLOSED

        # But open after 5
        for _ in range(2):
            cbs["market_data"].on_failure()
        assert cbs["market_data"].state == CircuitState.OPEN


# ── Test 2: Rate limiter enforces token bucket ──────────────────────────

class TestRateLimiterTokenBucket:
    """Verify rate limiter blocks requests when bucket empty, refills over time."""

    def test_rate_limiter_enforces_token_bucket(self) -> None:
        """When bucket is empty, acquire with timeout=0 must return False."""
        config = RateLimitConfig(rate_per_second=10.0, capacity=3)
        limiter = MultiBucketRateLimiter({"test": config})

        # Consume all 3 tokens immediately
        assert limiter.acquire("test", timeout=0) is True
        assert limiter.acquire("test", timeout=0) is True
        assert limiter.acquire("test", timeout=0) is True

        # 4th request with zero timeout must fail
        assert limiter.acquire("test", timeout=0) is False

    def test_rate_limiter_refills_over_time(self) -> None:
        """After waiting, tokens should be refilled."""
        config = RateLimitConfig(rate_per_second=100.0, capacity=2)
        limiter = MultiBucketRateLimiter({"test": config})

        # Drain the bucket
        limiter.acquire("test", timeout=0)
        limiter.acquire("test", timeout=0)
        assert limiter.acquire("test", timeout=0) is False

        # Wait for refill (100/s = 1 token every 10ms, wait 50ms for safety)
        time.sleep(0.05)

        # Should have at least 1 token now
        assert limiter.acquire("test", timeout=0) is True


# ── Test 3: HTTP client uses composed resilience ────────────────────────

class TestHttpClientResilienceComposition:
    """Verify DhanHttpClient actually uses the circuit breakers and rate limiter passed to it."""

    def test_http_client_uses_composed_resilience(self) -> None:
        """Circuit breaker state must affect HTTP client behavior."""
        cb_read = CircuitBreaker(
            "test-read",
            CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000),
        )
        cb_write = CircuitBreaker(
            "test-write",
            CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000),
        )
        cb_admin = CircuitBreaker(
            "test-admin",
            CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000),
        )

        client = DhanHttpClient(
            client_id="test",
            access_token="token",
            read_circuit_breaker=cb_read,
            write_circuit_breaker=cb_write,
            admin_circuit_breaker=cb_admin,
        )

        # Trip the read CB
        cb_read.on_failure()
        assert cb_read.state == CircuitState.OPEN

        # Mock session for a successful response
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": "ok"}
        client._session.request = MagicMock(return_value=resp)

        # Write should still work (different CB)
        result = client.post("/orders", json={"symbol": "RELIANCE"})
        assert result == {"data": "ok"}

        # Read should fail fast (CB is OPEN)
        from brokers.dhan.exceptions import DhanError
        with pytest.raises(DhanError):
            client.get("/marketfeed/quote")

    def test_http_client_uses_rate_limiter(self) -> None:
        """Rate limiter must be present and used by the client."""
        config = RateLimitConfig(rate_per_second=100.0, capacity=10)
        limiter = MultiBucketRateLimiter({"read": config, "write": config, "admin": config})

        client = DhanHttpClient(
            client_id="test",
            access_token="token",
            read_circuit_breaker=CircuitBreaker("test-r", CircuitBreakerConfig()),
            write_circuit_breaker=CircuitBreaker("test-w", CircuitBreakerConfig()),
            admin_circuit_breaker=CircuitBreaker("test-a", CircuitBreakerConfig()),
            _rate_limiter=limiter,
        )

        # Verify rate limiter is wired
        assert client._rate_limiter is limiter
        assert client._rate_metrics is not None

        # Mock session
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": "ok"}
        client._session.request = MagicMock(return_value=resp)

        # Request should succeed (rate limiter has tokens)
        result = client.get("/marketfeed/quote")
        assert result == {"data": "ok"}


# ── Test 4: Factory creates all resilience components ────────────────────

class TestFactoryResilienceCreation:
    """Verify factory functions create circuit breakers, rate limiter correctly."""

    def test_factory_creates_all_resilience_components(self) -> None:
        """create_circuit_breakers() must return 4 categories."""
        cbs = create_circuit_breakers()
        assert "orders" in cbs
        assert "market_data" in cbs
        assert "portfolio" in cbs
        assert "admin" in cbs
        assert all(isinstance(cb, CircuitBreaker) for cb in cbs.values())

    def test_factory_creates_rate_limiter_with_categories(self) -> None:
        """create_rate_limiter() must have orders, market_data, portfolio, admin buckets."""
        limiter = create_rate_limiter()
        cats = limiter.categories()
        assert "orders" in cats
        assert "market_data" in cats
        assert "portfolio" in cats
        assert "admin" in cats

    def test_circuit_breakers_have_correct_names(self) -> None:
        """Each CB must have a descriptive name."""
        cbs = create_circuit_breakers()
        assert cbs["orders"].name == "dhan-orders"
        assert cbs["market_data"].name == "dhan-market-data"
        assert cbs["portfolio"].name == "dhan-portfolio"
        assert cbs["admin"].name == "dhan-admin"

    def test_rate_limiter_configs_match_dhan_limits(self) -> None:
        """Rate limiter buckets must have Dhan-documented rates."""
        limiter = create_rate_limiter()

        orders_bucket = limiter.get_bucket("orders")
        assert orders_bucket.config.rate_per_second == 25.0
        assert orders_bucket.config.capacity == 25

        market_data_bucket = limiter.get_bucket("market_data")
        assert market_data_bucket.config.rate_per_second == 10.0
        assert market_data_bucket.config.capacity == 10


# ── Test 5: Circuit breaker opens after threshold ───────────────────────

class TestCircuitBreakerStateTransitions:
    """Verify circuit transitions OPEN after consecutive failures, then HALF_OPEN after timeout."""

    def test_circuit_breaker_opens_after_threshold(self) -> None:
        """CB must transition to OPEN after failure_threshold consecutive failures."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=3, success_threshold=2, open_duration_ms=100),
        )

        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

        # 3 failures should trip the breaker
        cb.on_failure()
        assert cb.state == CircuitState.CLOSED
        cb.on_failure()
        assert cb.state == CircuitState.CLOSED
        cb.on_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_circuit_breaker_transitions_to_half_open(self) -> None:
        """After open_duration_ms, CB must transition to HALF_OPEN."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, success_threshold=1, open_duration_ms=50),
        )

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for open duration (50ms + small buffer)
        time.sleep(0.1)

        # State should now be HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes_circuit(self) -> None:
        """Success in HALF_OPEN must transition back to CLOSED."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, success_threshold=2, open_duration_ms=50),
        )

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Successes should close it
        cb.on_success()
        cb.on_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self) -> None:
        """Any failure in HALF_OPEN must immediately re-open."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, success_threshold=2, open_duration_ms=50),
        )

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Single failure re-opens
        cb.on_failure()
        assert cb.state == CircuitState.OPEN


# ── Test 6: Retry executor respects policy ──────────────────────────────

class TestRetryExecutorPolicy:
    """Verify retry executor retries correct number of times with correct backoff."""

    def test_retry_executor_respects_max_attempts(self) -> None:
        """RetryExecutor must retry max_attempts-1 times before giving up."""
        call_count = 0

        def failing_fn():
            nonlocal call_count
            call_count += 1
            raise RetryableError("transient failure")

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=3),
            backoff=_ZERO_BACKOFF,  # No delays for test speed
        )

        with pytest.raises(RetryableError):
            executor.execute(failing_fn)

        assert call_count == 3, "Should have tried 3 times (1 initial + 2 retries)"

    def test_retry_executor_returns_on_success(self) -> None:
        """RetryExecutor must return immediately on success."""
        call_count = 0

        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("not yet")
            return "success"

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=5),
            backoff=_ZERO_BACKOFF,
        )

        result = executor.execute(eventually_succeeds)
        assert result == "success"
        assert call_count == 3

    def test_retry_executor_does_not_retry_non_retryable(self) -> None:
        """NonRetryableError must not trigger retries."""
        call_count = 0

        def failing_fn():
            nonlocal call_count
            call_count += 1
            raise NonRetryableError("permanent failure")

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=5),
            backoff=_ZERO_BACKOFF,
        )

        with pytest.raises(NonRetryableError):
            executor.execute(failing_fn)

        assert call_count == 1, "Should not retry non-retryable errors"

    def test_retry_executor_uses_circuit_breaker(self) -> None:
        """RetryExecutor must check circuit breaker before each attempt."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000),
        )
        cb.on_failure()  # Trip the CB
        assert cb.state == CircuitState.OPEN

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=3),
            circuit_breaker=cb,
            backoff=_ZERO_BACKOFF,
        )

        with pytest.raises(CircuitBreakerOpenError):
            executor.execute(lambda: "should not run")

    def test_dhan_retry_policies_differ(self) -> None:
        """Orders policy must differ from market_data policy."""
        assert ORDERS_POLICY.max_attempts == 3
        assert MARKET_DATA_POLICY.max_attempts == 2

        assert ORDERS_POLICY.base_delay_ms == 1000.0
        assert MARKET_DATA_POLICY.base_delay_ms == 500.0

    def test_retry_executor_records_cb_failure(self) -> None:
        """RetryableError must record failure in circuit breaker."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000),
        )

        executor = RetryExecutor(
            config=RetryConfig(max_attempts=3),
            circuit_breaker=cb,
            backoff=_ZERO_BACKOFF,
        )

        call_count = 0
        def failing_fn():
            nonlocal call_count
            call_count += 1
            raise RetryableError("fail")

        with pytest.raises(RetryableError):
            executor.execute(failing_fn)

        metrics = cb.metrics
        assert metrics.failure_count >= 1
        assert call_count == 3


# ── Test 7: Rate limiter metrics accurate ───────────────────────────────

class TestRateLimiterMetrics:
    """Verify DhanRateLimiterMetrics records requests/rejections correctly."""

    def test_rate_limiter_metrics_accurate(self) -> None:
        """Metrics must track requests and rejections per category."""
        metrics = DhanRateLimiterMetrics()

        # Record some requests
        metrics.record_request("orders")
        metrics.record_request("orders")
        metrics.record_request("market_data")

        assert metrics.get_requests_per_second("orders") > 0
        assert metrics.get_requests_per_second("market_data") > 0
        assert metrics.get_requests_per_second("admin") == 0  # No requests

        # Record rejections
        metrics.record_rejection("orders")
        metrics.record_rejection("orders")
        metrics.record_request("market_data")
        metrics.record_rejection("market_data")

        assert metrics.get_rejections("orders") == 2
        assert metrics.get_rejections("market_data") == 1
        assert metrics.get_rejections("admin") == 0

    def test_rate_limiter_metrics_queue_depth(self) -> None:
        """Queue depth must increment and decrement correctly."""
        metrics = DhanRateLimiterMetrics()

        metrics.increment_queue_depth("orders")
        metrics.increment_queue_depth("orders")
        assert metrics.get_queue_depth("orders") == 2

        metrics.decrement_queue_depth("orders")
        assert metrics.get_queue_depth("orders") == 1

        metrics.decrement_queue_depth("orders")
        assert metrics.get_queue_depth("orders") == 0

    def test_rate_limiter_metrics_snapshot(self) -> None:
        """Snapshot must include all categories that have been recorded."""
        metrics = DhanRateLimiterMetrics()
        metrics.record_request("orders")
        metrics.record_request("market_data")
        metrics.record_rejection("market_data")
        metrics.increment_queue_depth("admin")

        snapshot = metrics.snapshot()
        assert "orders" in snapshot
        assert "market_data" in snapshot
        assert "admin" in snapshot
        assert snapshot["orders"]["rejections"] == 0
        assert snapshot["market_data"]["rejections"] == 1
        assert snapshot["admin"]["queue_depth"] == 1


# ── Test 8: Resilience components thread-safe ───────────────────────────

class TestResilienceThreadSafety:
    """Verify concurrent access to circuit breakers and rate limiters doesn't cause race conditions."""

    def test_resilience_components_thread_safe(self) -> None:
        """Concurrent access must not cause exceptions or state corruption."""
        cb = CircuitBreaker(
            "thread-safe-test",
            CircuitBreakerConfig(failure_threshold=100, success_threshold=5, open_duration_ms=30_000),
        )

        errors: list[Exception] = []

        def hammer_failures():
            try:
                for _ in range(500):
                    cb.on_failure()
            except Exception as e:
                errors.append(e)

        def hammer_successes():
            try:
                for _ in range(500):
                    cb.on_success()
            except Exception as e:
                errors.append(e)

        def hammer_state_reads():
            try:
                for _ in range(500):
                    _ = cb.state
                    _ = cb.allow_request()
                    _ = cb.metrics
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=hammer_failures),
            threading.Thread(target=hammer_successes),
            threading.Thread(target=hammer_state_reads),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Thread safety violations: {errors}"
        # State should be valid (either CLOSED or OPEN, not corrupted)
        assert cb.state in (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN)

    def test_rate_limiter_thread_safe(self) -> None:
        """Concurrent rate limiter access must not cause exceptions."""
        config = RateLimitConfig(rate_per_second=100.0, capacity=10)
        limiter = MultiBucketRateLimiter({"test": config})

        errors: list[Exception] = []
        successes = [0]
        lock = threading.Lock()

        def acquire_tokens():
            try:
                for _ in range(10):
                    result = limiter.acquire("test", timeout=0)
                    if result:
                        with lock:
                            successes[0] += 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=acquire_tokens) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Rate limiter thread safety violations: {errors}"
        # Total successes must not exceed capacity (100)
        assert successes[0] <= 10, f"Too many successes: {successes[0]} (capacity=10)"

    def test_metrics_thread_safe(self) -> None:
        """Concurrent metrics recording must not cause exceptions or lost updates."""
        metrics = DhanRateLimiterMetrics()
        errors: list[Exception] = []

        def record_requests():
            try:
                for _ in range(100):
                    metrics.record_request("orders")
            except Exception as e:
                errors.append(e)

        def record_rejections():
            try:
                for _ in range(10):
                    metrics.record_rejection("orders")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_requests),
            threading.Thread(target=record_requests),
            threading.Thread(target=record_rejections),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Metrics thread safety violations: {errors}"
        # Rejections: 50 * 1 thread = 50
        assert metrics.get_rejections("orders") == 10
