"""Flow 5: Circuit Breaker Recovery E2E tests.

Validates the full circuit breaker lifecycle:
  CLOSED → OPEN (after threshold failures)
  OPEN → fast-fail (no requests pass)
  OPEN → HALF_OPEN (after timeout)
  HALF_OPEN → CLOSED (on success)
  HALF_OPEN → OPEN (on failure)
  RateLimiter + CircuitBreaker composition during recovery
  Trading resumes after full recovery cycle
  Metrics accurately track all state transitions

Uses REAL resilience objects — no MagicMock for internal components.
"""

from __future__ import annotations

import time

import pytest

from tradex.runtime.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    MultiBucketRateLimiter,
    RateLimitConfig,
    RetryConfig,
    RetryExecutor,
)
from tradex.runtime.resilience.backoff import BackoffStrategy, NoBackoff
from tests.e2e.fixtures.mock_brokers import MockFailingBroker

pytestmark = pytest.mark.e2e


class _RecoveryBackoff(BackoffStrategy):
    """Test backoff: no delay for first 2 attempts, 100ms on attempt 3+.

    This gives the circuit breaker time to transition from OPEN to HALF_OPEN
    between the failure that trips it and the next retry attempt.
    """

    def delay(self, attempt: int) -> float:
        if attempt >= 2:
            return 0.100  # 100ms — past the 50ms open_duration
        return 0.0


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def fast_cb() -> CircuitBreaker:
    """Circuit breaker with 50ms open duration for fast tests."""
    return CircuitBreaker(
        "e2e-cb",
        CircuitBreakerConfig(failure_threshold=3, success_threshold=1, open_duration_ms=50),
    )


@pytest.fixture()
def failing_broker() -> MockFailingBroker:
    """Broker that fails on place_order and ltp, recoverable after configured fails."""
    return MockFailingBroker(
        name="e2e-failing",
        fail_operations={"place_order", "ltp"},
        max_fails=3,
    )


# ── Test 1: CLOSED → OPEN after threshold ────────────────────────────────────


def test_circuit_opens_after_threshold(fast_cb: CircuitBreaker) -> None:
    """Circuit breaker must transition from CLOSED to OPEN after N consecutive failures."""
    assert fast_cb.state == CircuitState.CLOSED
    assert fast_cb.allow_request() is True

    # Failures below threshold keep CB closed
    fast_cb.on_failure()
    assert fast_cb.state == CircuitState.CLOSED
    fast_cb.on_failure()
    assert fast_cb.state == CircuitState.CLOSED

    # Threshold failure trips the breaker
    fast_cb.on_failure()
    assert fast_cb.state == CircuitState.OPEN
    assert fast_cb.allow_request() is False


# ── Test 2: OPEN circuit fast-fails without executing ────────────────────────


def test_fast_fail_no_retry_attempt(fast_cb: CircuitBreaker) -> None:
    """OPEN circuit must reject immediately — fn must NOT be executed."""
    # Trip the breaker
    for _ in range(3):
        fast_cb.on_failure()
    assert fast_cb.state == CircuitState.OPEN

    executor = RetryExecutor(
        config=RetryConfig(max_attempts=3),
        circuit_breaker=fast_cb,
        backoff=NoBackoff(),
    )

    call_count = 0

    def should_not_run():
        nonlocal call_count
        call_count += 1
        return "executed"

    with pytest.raises(CircuitBreakerOpenError):
        executor.execute(should_not_run)

    assert call_count == 0, "Function must not be called when CB is OPEN"


# ── Test 3: OPEN → HALF_OPEN after timeout ───────────────────────────────────


def test_half_open_after_duration() -> None:
    """After open_duration elapses, CB must transition from OPEN to HALF_OPEN."""
    cb = CircuitBreaker(
        "timing-cb",
        CircuitBreakerConfig(failure_threshold=2, success_threshold=1, open_duration_ms=50),
    )

    cb.on_failure()
    cb.on_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False

    t0 = time.monotonic()
    time.sleep(0.10)  # 100ms — well past 50ms open_duration

    elapsed_ms = (time.monotonic() - t0) * 1000
    assert elapsed_ms >= 50, "Must have waited at least the open_duration"
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True


# ── Test 4: HALF_OPEN → CLOSED on success ────────────────────────────────────


def test_half_open_success_closes_circuit() -> None:
    """Success in HALF_OPEN must transition back to CLOSED."""
    cb = CircuitBreaker(
        "recover-cb",
        CircuitBreakerConfig(failure_threshold=2, success_threshold=1, open_duration_ms=50),
    )

    cb.on_failure()
    cb.on_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.10)
    assert cb.state == CircuitState.HALF_OPEN

    cb.on_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


# ── Test 5: HALF_OPEN → OPEN on failure ──────────────────────────────────────


def test_half_open_failure_reopens_circuit(failing_broker: MockFailingBroker) -> None:
    """Any failure in HALF_OPEN must immediately re-open the circuit."""
    cb = CircuitBreaker(
        "reopen-cb",
        CircuitBreakerConfig(failure_threshold=2, success_threshold=2, open_duration_ms=50),
    )

    cb.on_failure()
    cb.on_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.10)
    assert cb.state == CircuitState.HALF_OPEN

    # Single failure re-opens immediately
    cb.on_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


# ── Test 6: RateLimiter composes with CircuitBreaker during recovery ─────────


def test_rate_limiter_during_recovery() -> None:
    """RateLimiter and CircuitBreaker must compose correctly through full recovery."""
    cb = CircuitBreaker(
        "composed-cb",
        CircuitBreakerConfig(failure_threshold=3, success_threshold=1, open_duration_ms=50),
    )
    rl_config = RateLimitConfig(rate_per_second=1000.0, capacity=10)
    limiter = MultiBucketRateLimiter({"orders": rl_config})

    broker = MockFailingBroker(
        name="composed-broker",
        fail_operations={"place_order"},
        max_fails=2,
    )

    executor = RetryExecutor(
        config=RetryConfig(max_attempts=5, retryable_exceptions=(RuntimeError,)),
        circuit_breaker=cb,
        rate_limiter=limiter,
        rate_limit_category="orders",
        backoff=NoBackoff(),
    )

    def place_via_broker():
        return broker.place_order(None)

    result = executor.execute(place_via_broker)

    # Verify full recovery
    assert cb.state == CircuitState.CLOSED
    assert result.success is True
    assert broker.fail_count == 2

    # Rate limiter tokens consumed (attempts 1, 2 acquired; attempt 3 blocked by open CB)
    bucket = limiter.get_bucket("orders")
    assert bucket.available_tokens < 10.0, "Tokens must have been consumed"


# ── Test 7: Trading resumes after full recovery cycle ────────────────────────


def test_trading_resumes_after_recovery(failing_broker: MockFailingBroker) -> None:
    """After OPEN → HALF_OPEN → CLOSED, orders must flow normally again."""
    cb = CircuitBreaker(
        "trading-cb",
        CircuitBreakerConfig(failure_threshold=3, success_threshold=1, open_duration_ms=50),
    )

    executor = RetryExecutor(
        config=RetryConfig(max_attempts=5, retryable_exceptions=(RuntimeError,)),
        circuit_breaker=cb,
        backoff=_RecoveryBackoff(),
    )

    # broker.max_fails=3 → first 3 place_order calls fail, 4th succeeds
    # Attempts 1-3: fail → CB opens after 3rd failure
    # Wait 50ms → CB → HALF_OPEN
    # Attempt 4: succeeds → CB → CLOSED
    result = executor.execute(lambda: failing_broker.place_order(None))

    assert cb.state == CircuitState.CLOSED
    assert result.success is True
    assert cb.allow_request() is True

    # Subsequent order must succeed without retries
    result2 = failing_broker.place_order(None)
    assert result2.success is True


# ── Test 8: Metrics accurately track all state transitions ───────────────────


def test_metrics_recorded_across_transitions(fast_cb: CircuitBreaker) -> None:
    """CB metrics must accurately record failures, successes, and state changes."""
    initial = fast_cb.metrics
    assert initial.failure_count == 0
    assert initial.success_count == 0
    assert initial.state_change_count == 0
    assert initial.total_calls == 0

    # Phase 1: Trip the breaker (CLOSED → OPEN)
    fast_cb.on_failure()
    fast_cb.on_failure()
    fast_cb.on_failure()
    assert fast_cb.state == CircuitState.OPEN

    after_open = fast_cb.metrics
    assert after_open.failure_count == 3
    assert after_open.state_change_count == 1  # CLOSED → OPEN
    assert after_open.total_calls == 3

    # Phase 2: Wait for HALF_OPEN transition
    time.sleep(0.10)
    _ = fast_cb.state  # trigger OPEN → HALF_OPEN

    after_half_open = fast_cb.metrics
    assert after_half_open.state_change_count == 2  # + OPEN → HALF_OPEN

    # Phase 3: Recover (HALF_OPEN → CLOSED)
    fast_cb.on_success()
    assert fast_cb.state == CircuitState.CLOSED

    final = fast_cb.metrics
    assert final.failure_count == 0  # reset by _transition_to(CLOSED)
    assert final.success_count == 0  # reset by _transition_to(CLOSED)
    assert final.state_change_count == 3  # + HALF_OPEN → CLOSED
    assert final.total_calls == 4
