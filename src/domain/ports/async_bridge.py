"""Async/sync bridge ports — wired by the runtime composition root."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")

_run_coro_sync: Callable[..., Any] | None = None
_new_dedicated_loop: Callable[[], Any] | None = None


def set_async_runner(fn: Callable[..., Any]) -> None:
    global _run_coro_sync
    _run_coro_sync = fn


def set_dedicated_loop_factory(fn: Callable[[], Any]) -> None:
    global _new_dedicated_loop
    _new_dedicated_loop = fn


def run_coro_sync(coro: Awaitable[T], *, timeout: float | None = None) -> T:
    if _run_coro_sync is None:
        raise RuntimeError(
            "Async runner not wired at composition root. "
            "Call domain.ports.async_bridge.set_async_runner() from runtime."
        )
    if timeout is not None:
        return _run_coro_sync(coro, timeout=timeout)
    return _run_coro_sync(coro)


def new_dedicated_loop() -> Any:
    if _new_dedicated_loop is None:
        raise RuntimeError(
            "Dedicated loop factory not wired at composition root. "
            "Call domain.ports.async_bridge.set_dedicated_loop_factory() from runtime."
        )
    return _new_dedicated_loop()

