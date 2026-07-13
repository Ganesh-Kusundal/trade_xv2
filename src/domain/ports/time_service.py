"""Clock port — domain-level boundary for time operations.

A single, injectable clock abstraction so that domain events, schedulers,
and time-dependent logic can run against a *virtual* clock in tests and
replay while defaulting to the real wall clock in production.

Why in domain
--------------
``DomainEvent`` (a domain value object) needs a clock without importing
infrastructure. The ``ClockPort`` Protocol and its default implementations
live here, keeping the dependency arrow clean: domain ← infrastructure
(never the reverse).

Usage
-----
    from domain.ports.time_service import get_current_clock, use_clock, VirtualClock

    # Production: real wall clock (default, no setup needed).
    now = get_current_clock().now()

    # Tests / replay: deterministic virtual clock.
    with use_clock(VirtualClock(initial=some_dt)):
        ...  # every DomainEvent.now() uses the virtual time
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from domain.ports.time_service_impls import RealClock


@runtime_checkable
class ClockPort(Protocol):
    """Protocol for time operations used across the runtime."""

    def now(self) -> datetime:
        """Return the current time as timezone-aware UTC."""

    def timestamp(self) -> float:
        """Return seconds since the Unix epoch (float)."""

    def epoch_ms(self) -> int:
        """Return milliseconds since the Unix epoch (int)."""

    def exchange_now(self, exchange: str) -> datetime:
        """Return the current time in ``exchange``'s local timezone."""


# Backward-compatible alias for the previous (dead) port name.
TimeServicePort = ClockPort


_REAL_CLOCK = RealClock()

_clock_var: contextvars.ContextVar[ClockPort | None] = contextvars.ContextVar(
    "clock", default=None
)


def get_current_clock() -> ClockPort:
    """Return the clock active on the current context (defaults to real time)."""
    return _clock_var.get() or _REAL_CLOCK


def set_current_clock(clock: ClockPort) -> None:
    """Set the clock for the current context."""
    _clock_var.set(clock)


@contextmanager
def use_clock(clock: ClockPort) -> Iterator[ClockPort]:
    """Context manager to run a block with a specific clock.

    Example::

        with use_clock(VirtualClock(initial=start)):
            event = DomainEvent.now(...)  # uses virtual time
    """
    token = _clock_var.set(clock)
    try:
        yield clock
    finally:
        _clock_var.reset(token)


# Backward-compatible re-exports — concrete clocks moved to
# domain.ports.time_service_impls. Import from there in new code.
import warnings as _warnings

def __getattr__(name: str):
    _CONCRETE = {"RealClock", "VirtualClock"}
    if name in _CONCRETE:
        from domain.ports import time_service_impls as _mod
        _warnings.warn(
            f"Importing {name!r} from domain.ports.time_service is deprecated. "
            f"Use domain.ports.time_service_impls instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
