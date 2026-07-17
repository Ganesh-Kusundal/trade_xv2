"""Application-layer ports for runtime services.

Defines callables that the runtime composition root injects at startup.
Application code uses these instead of importing from ``runtime.*``
directly, preserving the dependency rule (application may not import runtime).
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, TypeVar

T = TypeVar("T")

# Injected by runtime at startup (see runtime/trading_runtime_factory.py).
_run_coro_sync: Any = None


def set_async_runner(fn: Any) -> None:
    """Register the async-to-sync bridge (called by runtime at startup)."""
    global _run_coro_sync
    _run_coro_sync = fn


def run_coro_sync(coro: Awaitable[T], *, timeout: float | None = None) -> T:
    """Run a coroutine from a sync context via the runtime event loop.

    Raises RuntimeError if the runner has not been injected yet.
    """
    if _run_coro_sync is None:
        raise RuntimeError(
            "Async runner not wired at composition root. "
            "Call application.ports.set_async_runner() from runtime at startup."
        )
    if timeout is not None:
        return _run_coro_sync(coro, timeout=timeout)
    return _run_coro_sync(coro)
