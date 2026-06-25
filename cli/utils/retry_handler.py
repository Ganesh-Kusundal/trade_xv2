"""Retry handler with exponential backoff for CLI commands.

Provides automatic retry logic for transient failures (network errors, rate limits).

Usage:
    from cli.utils.retry_handler import with_retry

    @with_retry(max_retries=3, backoff_factor=1.0)
    def fetch_quote(symbol):
        return gw.quote(symbol)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# Default retryable exceptions
DEFAULT_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def with_retry(
    func: Callable | None = None,
    *,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    retryable_errors: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_ERRORS,
    on_retry: Callable | None = None,
) -> Callable:
    """Decorator to retry failed operations with exponential backoff.

    Parameters
    ----------
    func :
        Function to wrap (used when decorator is applied without parentheses).
    max_retries :
        Maximum number of retry attempts.
    backoff_factor :
        Multiplier for exponential backoff. Wait time = backoff_factor * (2 ** attempt).
    retryable_errors :
        Tuple of exception types that should trigger a retry.
    on_retry :
        Optional callback invoked on each retry: on_retry(attempt, exc, wait_time).

    Returns
    -------
    Callable
        Wrapped function with retry logic.

    Examples
    --------
    >>> from cli.utils.retry_handler import with_retry
    >>>
    >>> @with_retry(max_retries=3, backoff_factor=1.0)
    ... def fetch_quote(symbol):
    ...     return gw.quote(symbol)
    >>>
    >>> quote = fetch_quote("RELIANCE")  # Retries up to 3 times on failure
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retryable_errors as exc:
                    last_exc = exc
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor * (2**attempt)
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

            # Should never reach here, but satisfy type checker
            raise last_exc  # type: ignore[misc]

        return wrapper

    # Support both @with_retry and @with_retry() syntax
    if func is not None:
        return decorator(func)
    return decorator


def retry_with_backoff(
    func: Callable,
    *args: Any,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    retryable_errors: tuple[type[Exception], ...] = DEFAULT_RETRYABLE_ERRORS,
    **kwargs: Any,
) -> Any:
    """Execute function with retry logic (non-decorator version).

    Parameters
    ----------
    func :
        Callable to execute.
    *args :
        Positional arguments to pass to func.
    max_retries :
        Maximum number of retry attempts.
    backoff_factor :
        Multiplier for exponential backoff.
    retryable_errors :
        Tuple of exception types that should trigger a retry.
    **kwargs :
        Keyword arguments to pass to func.

    Returns
    -------
    Any
        Return value of func.

    Raises
    ------
    Exception
        Last exception if all retries exhausted.

    Examples
    --------
    >>> from cli.utils.retry_handler import retry_with_backoff
    >>>
    >>> quote = retry_with_backoff(
    ...     gw.quote,
    ...     "RELIANCE",
    ...     max_retries=3,
    ...     backoff_factor=1.0,
    ... )
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except retryable_errors as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2**attempt)
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
