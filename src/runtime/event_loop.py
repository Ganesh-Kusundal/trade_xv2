"""Centralized event-loop acquisition boundary (DR-E2 / TOS-P5-010).

Background
----------
The platform mixes threads and asyncio heavily: broker WebSocket threads,
TUI/CLI loop threads, and worker threads all need to drive async coroutines.
Historically each such site called ``asyncio.new_event_loop()`` ad hoc.
That scatters loop ownership across the codebase.

This module is the **single sanctioned boundary** for creating or acquiring
event loops:

* :func:`ensure_runtime_loop` / :func:`get_runtime_loop` — process-wide loop
* :func:`run_coro_sync` — run a coroutine from a sync context without
  ad-hoc ``new_event_loop`` at the call site
* :func:`new_dedicated_loop` — long-lived loop owned by a single thread
  (HTTP metrics server, depth feed) that is *not* the process runtime loop

``asyncio.new_event_loop()`` must never appear outside this module.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable
from typing import TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    "assert_single_loop_boundary",
    "ensure_runtime_loop",
    "get_runtime_loop",
    "new_dedicated_loop",
    "run_coro_sync",
    "set_runtime_loop",
]

T = TypeVar("T")

# Process-wide singular runtime loop and the discipline lock guarding it.
_RUNTIME_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def ensure_runtime_loop() -> asyncio.AbstractEventLoop:
    """Return the process-wide runtime loop, creating it ONCE if needed.

    Must be invoked from the loop-owning thread (the ``Runtime`` composition
    root) before worker threads try to schedule work onto it.
    """
    global _RUNTIME_LOOP
    with _LOOP_LOCK:
        if _RUNTIME_LOOP is None or _RUNTIME_LOOP.is_closed():
            _RUNTIME_LOOP = asyncio.new_event_loop()
        return _RUNTIME_LOOP


def set_runtime_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Register an already-running loop as the runtime loop."""
    global _RUNTIME_LOOP
    with _LOOP_LOCK:
        _RUNTIME_LOOP = loop


def get_runtime_loop() -> asyncio.AbstractEventLoop:
    """Acquire the runtime loop without creating one.

    Raises:
        RuntimeError: If no runtime loop has been established yet.
    """
    loop = _RUNTIME_LOOP
    if loop is None or loop.is_closed():
        raise RuntimeError(
            "Runtime event loop has not been established. Establish it from "
            "the loop-owning thread via runtime.event_loop.ensure_runtime_loop() "
            "or set_runtime_loop(), then acquire it from worker threads."
        )
    return loop


def new_dedicated_loop() -> asyncio.AbstractEventLoop:
    """Create a loop owned by a single dedicated thread.

    Use for long-lived servers/feeds that call ``run_forever`` / own their
    lifecycle. Do **not** use for one-shot ``run_until_complete`` — use
    :func:`run_coro_sync` instead.
    """
    return asyncio.new_event_loop()


def run_coro_sync(coro: Awaitable[T], *, timeout: float | None = None) -> T:
    """Run *coro* to completion from a synchronous context.

    Prefer the process runtime loop when established (and running, via
    ``run_coroutine_threadsafe``). Otherwise use a short-lived loop created
    only inside this module.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None:
        # Called from inside a running loop — schedule and block (caller must
        # not be the loop thread if they need the result, or they deadlock).
        future = asyncio.run_coroutine_threadsafe(coro, running)
        return future.result(timeout=timeout)

    # Prefer established runtime loop.
    with _LOOP_LOCK:
        loop = _RUNTIME_LOOP
    if loop is not None and not loop.is_closed():
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=timeout)
        return loop.run_until_complete(coro)

    # No runtime loop yet: ephemeral loop (still only created here).
    ephemeral = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(ephemeral)
        return ephemeral.run_until_complete(coro)
    finally:
        try:
            ephemeral.close()
        except Exception as exc:  # pragma: no cover
            logger.debug("ephemeral_loop_close_failed: %s", exc)
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass


def assert_single_loop_boundary() -> list[str]:
    """Guard: report any tasks scheduled on a non-runtime loop."""
    violations: list[str] = []
    runtime_loop = _RUNTIME_LOOP
    try:
        tasks = asyncio.all_tasks()
    except RuntimeError:
        return violations
    for task in tasks:
        owner = getattr(task, "_loop", None)
        if owner is None:
            continue
        if runtime_loop is None or owner is not runtime_loop:
            violations.append(f"task {task!r} scheduled on non-runtime loop {owner!r}")
    return violations
