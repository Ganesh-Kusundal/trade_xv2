"""Async utilities for bridging sync and async code.

Provides helpers for safely running async coroutines from synchronous contexts,
with proper detection of existing event loops to avoid RuntimeError.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Get the current event loop, or create a new one if none exists.

    Returns:
        The current or newly created event loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Safely run an async coroutine from synchronous code.

    Detects whether the caller is already inside a running event loop.
    If so, the coroutine is executed in a dedicated worker thread with its
    own event loop to avoid ``RuntimeError: This event loop is already running``.
    Otherwise, ``asyncio.run()`` is used directly.

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.

    Raises:
        Any exception raised by the coroutine is re-raised in the caller's thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — safe to use asyncio.run()
        return asyncio.run(coro)

    # We are inside a running event loop — offload to a worker thread
    # with its own event loop to avoid deadlocking the current loop.
    result: Any = None
    exception: BaseException | None = None

    def _run_in_thread() -> None:
        nonlocal result, exception
        thread_loop = asyncio.new_event_loop()
        try:
            result = thread_loop.run_until_complete(coro)
        except BaseException as exc:
            exception = exc
        finally:
            thread_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_in_thread)
        future.result()  # block until the worker thread finishes

    if exception is not None:
        raise exception
    return result
