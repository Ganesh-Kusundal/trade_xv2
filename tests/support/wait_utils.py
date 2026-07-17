"""Shared polling utilities for async/eventual consistency in tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def wait_until(
    condition: Callable[[], T],
    *,
    timeout: float = 5.0,
    interval: float = 0.05,
    message: str = "Condition not met",
) -> T:
    """Poll *condition* until it returns a truthy value, then return it.

    Raises ``TimeoutError`` after *timeout* seconds if the condition
    never becomes truthy.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = condition()
        if result:
            return result
        if time.monotonic() > deadline:
            raise TimeoutError(message)
        time.sleep(interval)


def wait_until_no_exception(
    fn: Callable[[], T],
    *,
    timeout: float = 5.0,
    interval: float = 0.05,
    message: str = "Function still raises",
) -> T:
    """Poll *fn* until it stops raising, then return its result.

    Useful for waiting until a background thread has completed its work.
    """
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while True:
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if time.monotonic() > deadline:
                raise TimeoutError(f"{message}: {last_exc}") from last_exc
            time.sleep(interval)


async def async_wait_until(
    condition: Callable[[], Awaitable[T]],
    *,
    timeout: float = 5.0,
    interval: float = 0.05,
    message: str = "Condition not met",
) -> T:
    """Async version of wait_until. Poll *condition* until it returns a truthy value."""
    deadline = time.monotonic() + timeout
    while True:
        result = await condition()
        if result:
            return result
        if time.monotonic() > deadline:
            raise TimeoutError(message)
        await asyncio.sleep(interval)
