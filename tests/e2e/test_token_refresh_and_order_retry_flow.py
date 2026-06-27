"""Flow 4: Token Refresh → Order Retry E2E tests.

Validates the full token-refresh and order-retry lifecycle:
  Expired token detection triggers refresh
  401 → refresh → retry succeeds
  Auth errors don't trip circuit breaker prematurely
  Exponential backoff delays increase correctly
  Order succeeds within retry window
  Order fails after retry exhaustion → DLQ
  Full reconciliation after auth recovery

Uses REAL resilience objects — no MagicMock for internal components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from brokers.common.resilience import (
    AuthenticationError,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    NoBackoff,
    RetryConfig,
    RetryExecutor,
)
from brokers.common.resilience.backoff import ExponentialBackoff
from infrastructure.event_bus import DeadLetterQueue, DomainEvent, EventBus
from tests.e2e.fixtures.event_capturer import EventCapturer
from tests.e2e.fixtures.trading_context_factory import create_test_trading_context


pytestmark = pytest.mark.e2e


# ── Helpers ───────────────────────────────────────────────────────────────────


@dataclass
class MockAuthRefreshBroker:
    """Mock broker that raises AuthenticationError on first N calls.

    Simulates token expiry → refresh → retry flow.
    """

    name: str = "auth-refresh"
    max_auth_fails: int = 1
    fail_count: int = 0

    def place_order(self, request: Any) -> dict:
        if self.fail_count < self.max_auth_fails:
            self.fail_count += 1
            raise AuthenticationError("Token expired (simulated)")
        return {"order_id": "AUTH-OK-001", "status": "FILLED"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def fast_exp_backoff() -> ExponentialBackoff:
    """Exponential backoff with 1ms base — fast, but produces increasing delays."""
    return ExponentialBackoff(
        base_delay_ms=1.0,
        max_delay_ms=100.0,
        multiplier=2.0,
        jitter_factor=0.0,
    )


@pytest.fixture()
def auth_refresh_broker() -> MockAuthRefreshBroker:
    """Broker that fails once with AuthenticationError, then succeeds."""
    return MockAuthRefreshBroker(max_auth_fails=1)


@pytest.fixture()
def failing_broker():
    """MockFailingBroker that fails on place_order, recoverable after 2 fails."""
    from tests.e2e.fixtures.mock_brokers import MockFailingBroker

    return MockFailingBroker(
        name="e2e-auth-failing",
        fail_operations={"place_order"},
        max_fails=2,
    )


@pytest.fixture()
def trading_ctx():
    """Fresh TradingContext with EventBus and DeadLetterQueue."""
    return create_test_trading_context()


# ── Test 1: Expired token → refresh triggered ────────────────────────────────


def test_token_expiry_detection(auth_refresh_broker: MockAuthRefreshBroker) -> None:
    """Expired token (AuthenticationError) must trigger retry (refresh)."""
    refresh_triggered = False

    def on_retry(attempt: int, exc: Exception) -> None:
        nonlocal refresh_triggered
        refresh_triggered = True

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=3,
            retryable_exceptions=(AuthenticationError,),
        ),
        backoff=NoBackoff(),
        on_retry=on_retry,
    )

    result = executor.execute(lambda: auth_refresh_broker.place_order(None))

    assert refresh_triggered is True, "Token refresh must have been triggered"
    assert auth_refresh_broker.fail_count == 1
    assert result["status"] == "FILLED"


# ── Test 2: 401 → refresh → retry succeeds ──────────────────────────────────


def test_order_retry_after_token_refresh(
    auth_refresh_broker: MockAuthRefreshBroker,
) -> None:
    """After 401 → token refresh → order retry must succeed."""
    retry_attempts: list[int] = []

    def on_retry(attempt: int, exc: Exception) -> None:
        retry_attempts.append(attempt)

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=3,
            retryable_exceptions=(AuthenticationError,),
        ),
        backoff=NoBackoff(),
        on_retry=on_retry,
    )

    result = executor.execute(lambda: auth_refresh_broker.place_order(None))

    assert result["status"] == "FILLED"
    assert result["order_id"] == "AUTH-OK-001"
    assert len(retry_attempts) == 1
    assert retry_attempts[0] == 0


# ── Test 3: Auth error → CB stays CLOSED ─────────────────────────────────────


def test_circuit_breaker_not_trip_on_auth(
    auth_refresh_broker: MockAuthRefreshBroker,
) -> None:
    """Single auth error must NOT trip circuit breaker (threshold not reached)."""
    cb = CircuitBreaker(
        "auth-cb",
        CircuitBreakerConfig(failure_threshold=5, success_threshold=1, open_duration_ms=1000),
    )

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=3,
            retryable_exceptions=(AuthenticationError,),
        ),
        circuit_breaker=cb,
        backoff=NoBackoff(),
    )

    result = executor.execute(lambda: auth_refresh_broker.place_order(None))

    assert result["status"] == "FILLED"
    assert cb.state == CircuitState.CLOSED
    assert cb.metrics.failure_count == 0  # reset by on_success


# ── Test 4: Exponential delay between retries ────────────────────────────────


def test_retry_executor_backoff(fast_exp_backoff: ExponentialBackoff) -> None:
    """Retry delays must increase exponentially with attempt number."""
    broker = MockAuthRefreshBroker(max_auth_fails=4)

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=5,
            retryable_exceptions=(AuthenticationError,),
        ),
        backoff=fast_exp_backoff,
    )

    captured_delays: list[float] = []

    with patch("brokers.common.resilience.retry.time.sleep") as mock_sleep:
        mock_sleep.side_effect = lambda d: captured_delays.append(d)
        result = executor.execute(lambda: broker.place_order(None))

    assert result["status"] == "FILLED"
    assert len(captured_delays) == 4

    # ExponentialBackoff(base=1ms, multiplier=2.0, jitter=0):
    #   attempt 0 → 1ms, attempt 1 → 2ms, attempt 2 → 4ms, attempt 3 → 8ms
    for i in range(len(captured_delays) - 1):
        assert captured_delays[i + 1] > captured_delays[i], (
            f"Delay must increase: delay[{i}]={captured_delays[i]}, "
            f"delay[{i+1}]={captured_delays[i+1]}"
        )


# ── Test 5: Order succeeds within retry window ───────────────────────────────


def test_order_eventually_placed(
    failing_broker,
) -> None:
    """Order must succeed within the retry window after transient failures."""
    cb = CircuitBreaker(
        "order-cb",
        CircuitBreakerConfig(failure_threshold=5, success_threshold=1, open_duration_ms=1000),
    )

    retry_count = 0

    def on_retry(attempt: int, exc: Exception) -> None:
        nonlocal retry_count
        retry_count += 1

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=5,
            retryable_exceptions=(RuntimeError,),
        ),
        circuit_breaker=cb,
        backoff=NoBackoff(),
        on_retry=on_retry,
    )

    result = executor.execute(lambda: failing_broker.place_order(None))

    assert result.success is True
    assert result.order_id == "OK-001"
    assert retry_count == 2  # 2 failures before success
    assert failing_broker.fail_count == 2
    assert cb.state == CircuitState.CLOSED


# ── Test 6: Exhausted → FAILED + DLQ ─────────────────────────────────────────


def test_order_fails_after_retry_exhaustion() -> None:
    """Exhausted retries must publish ORDER_FAILED and route to DLQ."""
    from brokers.common.observability.event_metrics import EventMetrics
    from tests.e2e.fixtures.mock_brokers import MockFailingBroker

    broker = MockFailingBroker(
        name="always-fail",
        fail_operations={"place_order"},
        max_fails=-1,  # fail forever
    )

    # Construct EventBus + DLQ directly so we hold a reference to the
    # exact same DLQ instance (TradingContext.__init__ replaces an empty
    # DLQ via `or create_default_dead_letter_queue()`).
    dlq = DeadLetterQueue(max_size=100)
    metrics = EventMetrics()
    event_bus = EventBus(metrics=metrics, dead_letter_queue=dlq)

    capturer = EventCapturer(event_bus)
    capturer.subscribe("ORDER_FAILED")

    # Handler that raises on ORDER_FAILED → event goes to DLQ
    def failing_handler(event: DomainEvent) -> None:
        raise RuntimeError("DLQ routing test")

    event_bus.subscribe("ORDER_FAILED", failing_handler)

    def on_failure(exc: Exception) -> None:
        event_bus.publish(
            DomainEvent.now(
                "ORDER_FAILED",
                {"error": str(exc), "symbol": "RELIANCE"},
            )
        )

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=3,
            retryable_exceptions=(RuntimeError,),
        ),
        backoff=NoBackoff(),
        on_failure=on_failure,
    )

    with pytest.raises(RuntimeError, match="always-fail"):
        executor.execute(lambda: broker.place_order(None))

    # ORDER_FAILED event was published
    capturer.assert_event_published("ORDER_FAILED", min_count=1)

    # DLQ captured the handler failure
    assert len(dlq) == 1
    dead_letter = dlq.peek(1)[0]
    assert dead_letter.event.event_type == "ORDER_FAILED"
    assert dead_letter.error_type == "RuntimeError"


# ── Test 7: Order confirmed post-recovery ────────────────────────────────────


def test_reconciliation_after_auth_recovery(
    failing_broker,
    trading_ctx,
) -> None:
    """Full flow: failures → retries → success → reconciliation events."""
    event_bus = trading_ctx.event_bus

    capturer = EventCapturer(event_bus)
    capturer.subscribe("ORDER_PLACED", "ORDER_FAILED")

    cb = CircuitBreaker(
        "recovery-cb",
        CircuitBreakerConfig(failure_threshold=5, success_threshold=1, open_duration_ms=1000),
    )

    retry_count = 0

    def on_retry(attempt: int, exc: Exception) -> None:
        nonlocal retry_count
        retry_count += 1

    executor = RetryExecutor(
        config=RetryConfig(
            max_attempts=5,
            retryable_exceptions=(RuntimeError,),
        ),
        circuit_breaker=cb,
        backoff=NoBackoff(),
        on_retry=on_retry,
    )

    result = executor.execute(lambda: failing_broker.place_order(None))

    # Publish reconciliation event
    event_bus.publish(
        DomainEvent.now(
            "ORDER_PLACED",
            {"order_id": result.order_id, "status": "FILLED"},
        )
    )

    # Verify retry happened
    assert retry_count == 2
    assert result.success is True

    # Verify reconciliation event
    capturer.assert_event_published("ORDER_PLACED", min_count=1)
    capturer.assert_event_payload_matches(
        "ORDER_PLACED",
        {"order_id": "OK-001", "status": "FILLED"},
    )

    # No failure events
    assert capturer.count("ORDER_FAILED") == 0

    # CB recovered to CLOSED
    assert cb.state == CircuitState.CLOSED
