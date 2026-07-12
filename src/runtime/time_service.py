"""Injectable time service for the runtime.

Provides :class:`TimeService`, which delegates ``now()`` to an injected
:class:`~domain.primitives.value_objects.Clock`. Two concrete clocks ship here:

* :class:`SystemClock` — the real wall clock (calls ``datetime.now``). This is
  the **default** implementation and is used in production. It lives in the
  runtime/infrastructure layer, *not* in the domain VO module, so domain code
  never reaches for ``datetime`` directly.
* :class:`FakeClock` — a deterministic, controllable clock for tests and replay
  (set / advance / freeze).

Domain and application code must receive a ``TimeService`` (or ``Clock``) via
dependency injection and call ``time_service.now()``; they must never call
``datetime.now()`` themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Union

from domain.primitives.value_objects import Clock

ClockSource = Union[Clock, Callable[[], datetime], Any]


class SystemClock:
    """Real wall-clock implementation (the production default)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """Deterministic, controllable clock for tests, replay, and simulation.

    Holds an internal timezone-aware UTC ``datetime`` that can be set or
    advanced. Every ``now()`` returns the current virtual time, so callers get
    fully reproducible timestamps, scheduling, and reconciliation loops.
    """

    def __init__(self, initial: datetime | None = None) -> None:
        if initial is None:
            initial = datetime(2000, 1, 1, tzinfo=timezone.utc)
        elif initial.tzinfo is None:
            initial = initial.replace(tzinfo=timezone.utc)
        self._current = initial

    def now(self) -> datetime:
        return self._current

    def set(self, value: datetime) -> None:
        """Set the virtual time absolutely (naive values treated as UTC)."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        self._current = value

    def advance(self, delta: timedelta) -> None:
        """Advance the virtual time by ``delta``."""
        self._current = self._current + delta

    @property
    def current(self) -> datetime:
        return self._current


def _wrap(source: ClockSource | None) -> Clock:
    """Coerce an injected source into a :class:`Clock`."""
    if source is None:
        return Clock(_now=SystemClock().now)
    if isinstance(source, Clock):
        return source
    # A clock instance exposing a `now()` callable (SystemClock/FakeClock/...).
    if hasattr(source, "now") and callable(getattr(source, "now")):
        return Clock(_now=source.now)
    if callable(source):
        return Clock(_now=source)
    raise TypeError(f"cannot build a Clock from {type(source).__name__!r}")


@dataclass
class TimeService:
    """Injectable time service. Delegates ``now()`` to an injected ``Clock``.

    Construction defaults to the real wall clock (``SystemClock``). For
    deterministic tests, inject a :class:`FakeClock` or any ``now`` callable via
    ``TimeService.with_clock(...)``.
    """

    clock: Clock = field(default_factory=lambda: Clock(_now=SystemClock().now))

    @classmethod
    def with_clock(cls, source: ClockSource) -> "TimeService":
        """Build a ``TimeService`` around an injected clock source.

        Accepts a :class:`Clock`, a ``Clock``-like instance with a ``now()``
        method (e.g. :class:`FakeClock`), or a bare ``Callable[[], datetime]``.
        """
        return cls(clock=_wrap(source))

    def now(self) -> datetime:
        """Return the current time from the injected clock."""
        return self.clock.now()

    def now_utc(self) -> datetime:
        """Alias for :meth:`now` (results are timezone-aware UTC)."""
        return self.clock.now()


__all__ = ["FakeClock", "SystemClock", "TimeService"]
