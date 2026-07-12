"""Retry handler with exponential backoff for CLI commands.

Provides automatic retry logic for transient failures (network errors, rate limits).

Usage:
    from interface.ui.utils.retry_handler import with_retry

    @with_retry(max_retries=3, backoff_factor=1.0)
    def fetch_quote(symbol):
        return session.stock(symbol).refresh()
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from domain.constants.resilience import MAX_RETRY_ATTEMPTS, RETRY_BASE_DELAY_MS

logger = logging.getLogger(__name__)

#: Default base wait (seconds) for exponential backoff; maps RETRY_BASE_DELAY_MS.
DEFAULT_BACKOFF_FACTOR: float = RETRY_BASE_DELAY_MS / 1000.0

DEFAULT_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def _execute_with_retry(
    func: Callable,
    args: tuple,
    kwargs: dict,
    *,
    max_retries: int,
    backoff_factor: float,
    retryable_errors: tuple[type[Exception], ...],
    on_retry: Callable | None = None,
) -> Any:
    """Core retry loop shared by the decorator and standalone function."""
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except retryable_errors as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(
                    "retry_attempt",
                    extra={
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": str(exc),
                        "wait_time": wait_time,
                    },
                )
                if on_retry is not None:
                    on_retry(attempt, exc, wait_time)
                time.sleep(wait_time)
            else:
                logger.error(
                    "retry_exhausted",
                    extra={
                        "function": func.__name__,
                        "attempts": max_retries,
                        "error": str(exc),
                    },
                )

    raise last_exc  # type: ignore[misc]


def with_retry(
    func: Callable | None = None,
    *,
    max_retries: int = MAX_RETRY_ATTEMPTS,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retryable_errors: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_ERRORS,
    on_retry: Callable | None = None,
) -> Callable:
    """Decorator to retry failed operations with exponential backoff."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _execute_with_retry(
                func, args, kwargs,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                retryable_errors=retryable_errors,
                on_retry=on_retry,
            )
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def retry_with_backoff(
    func: Callable,
    *args: Any,
    max_retries: int = MAX_RETRY_ATTEMPTS,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retryable_errors: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_ERRORS,
    **kwargs: Any,
) -> Any:
    """Execute function with retry logic (non-decorator version)."""
    return _execute_with_retry(
        func, args, kwargs,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        retryable_errors=retryable_errors,
    )
