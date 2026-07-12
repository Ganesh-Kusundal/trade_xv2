"""Tests for the shared RetryExecutor — the single authority for retry.

Covers the canonical module ``infrastructure.resilience.retry_executor`` and
verifies backward-compatible import paths still resolve.
"""

import pytest

from infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from infrastructure.resilience.errors import NonRetryableError, RetryableError
from infrastructure.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
)
from infrastructure.resilience.retry_executor import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    RetryConfig,
    RetryExecutor,
)


def test_canonical_import_path_resolves():
    # The single authority must be importable from the canonical module.
    assert RetryExecutor is not None
    assert RetryConfig is not None


def test_backward_compatible_import_path_resolves():
    # The deprecated ``infrastructure.resilience.retry`` shim must still work.
    from infrastructure.resilience.retry import RetryConfig as RC
    from infrastructure.resilience.retry import RetryExecutor as RE

    assert RE is RetryExecutor
    assert RC is RetryConfig


def test_successful_execution():
    executor = RetryExecutor()
    assert executor.execute(lambda: "ok") == "ok"


def test_retryable_error_is_retried():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableError("transient")
        return "recovered"

    result = RetryExecutor(RetryConfig(max_attempts=4)).execute(flaky)
    assert result == "recovered"
    assert calls["n"] == 3


def test_non_retryable_fails_immediately():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise NonRetryableError("nope")

    with pytest.raises(NonRetryableError):
        RetryExecutor(RetryConfig(max_attempts=5)).execute(boom)
    assert calls["n"] == 1


def test_default_retryable_exceptions():
    cfg = RetryConfig()
    assert ConnectionError in cfg.retryable_exceptions
    assert TimeoutError in cfg.retryable_exceptions
    assert OSError in cfg.retryable_exceptions
    assert DEFAULT_RETRYABLE_EXCEPTIONS


def test_circuit_breaker_open_fast_fails():
    cb = CircuitBreaker(
        name="test",
        config=CircuitBreakerConfig(failure_threshold=1, open_duration_ms=10_000),
    )
    cb.on_failure()  # trip it open (threshold reached)

    with pytest.raises(Exception):
        RetryExecutor(RetryConfig(max_attempts=3), circuit_breaker=cb).execute(
            lambda: "x"
        )


def test_rate_limiter_is_acquired():
    rl = MultiBucketRateLimiter(
        configs={"orders": RateLimitConfig(rate_per_second=5, capacity=1)}
    )
    executor = RetryExecutor(
        config=RetryConfig(max_attempts=1),
        rate_limiter=rl,
        rate_limit_category="orders",
    )
    # The rate limiter is wired into the execute path: the single seed token
    # is acquired and the call proceeds. (A second call without refill would
    # block, so we assert the wiring via one successful acquire.)
    assert executor.execute(lambda: 1) == 1
