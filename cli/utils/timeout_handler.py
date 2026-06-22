"""Timeout handler for CLI commands.

Provides timeout protection for all API calls to prevent CLI hangs.

Usage:
    from cli.utils.timeout_handler import with_timeout

    try:
        quote = with_timeout(gw.quote, timeout_seconds=10, symbol="RELIANCE")
    except TimeoutError:
        console.print("[red]Quote request timed out after 10s[/red]")
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable

logger = logging.getLogger(__name__)


def with_timeout(
    func: Callable,
    timeout_seconds: int = 30,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute function with timeout, raise TimeoutError if exceeded.

    Parameters
    ----------
    func :
        Callable to execute.
    timeout_seconds :
        Maximum execution time in seconds.
    *args :
        Positional arguments to pass to func.
    **kwargs :
        Keyword arguments to pass to func.

    Returns
    -------
    Any
        Return value of func.

    Raises
    ------
    TimeoutError
        If func does not complete within timeout_seconds.
    Exception
        Any exception raised by func.

    Examples
    --------
    >>> from cli.utils.timeout_handler import with_timeout
    >>> try:
    ...     quote = with_timeout(gw.quote, timeout_seconds=10, symbol="RELIANCE")
    ... except TimeoutError:
    ...     print("Quote timed out")
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeout:
            logger.error(
                "timeout_exceeded",
                extra={
                    "function": func.__name__,
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise TimeoutError(
                f"{func.__name__} timed out after {timeout_seconds}s"
            )


def with_timeout_async(
    func: Callable,
    timeout_seconds: int = 30,
    on_timeout: Callable | None = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute function with timeout and optional fallback.

    Parameters
    ----------
    func :
        Callable to execute.
    timeout_seconds :
        Maximum execution time in seconds.
    on_timeout :
        Optional fallback callable to invoke on timeout.
    *args :
        Positional arguments to pass to func.
    **kwargs :
        Keyword arguments to pass to func.

    Returns
    -------
    Any
        Return value of func, or on_timeout() if timed out.
    """
    try:
        return with_timeout(func, timeout_seconds, *args, **kwargs)
    except TimeoutError:
        if on_timeout is not None:
            return on_timeout()
        raise
