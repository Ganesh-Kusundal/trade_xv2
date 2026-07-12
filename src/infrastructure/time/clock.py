"""Runtime clock facade for streaming / composer / provenance.

Application modules should import the shared singleton from here::

    from infrastructure.time.clock import time_service

This re-exports the canonical :class:`~infrastructure.time_service.TimeService`
instance so wall-clock reads share one object with
``infrastructure.time_service.time_service`` (exchange calendars, epoch helpers).

``now()`` is always timezone-aware UTC. Do not use naive ``datetime.now()`` for
order, audit, or stream timestamps — use ``time_service.now()`` or
``time_service.exchange_now(exchange)`` for exchange-local time.
"""

from __future__ import annotations

from domain.ports.time_service import (
    ClockPort,
    RealClock,
    VirtualClock,
    get_current_clock,
    set_current_clock,
    use_clock,
)
from infrastructure.time_service import TimeService, time_service

# Backward-compatible name: same class as the full TimeService.
Clock = TimeService

__all__ = [
    "Clock",
    "ClockPort",
    "RealClock",
    "TimeService",
    "VirtualClock",
    "get_current_clock",
    "set_current_clock",
    "time_service",
    "use_clock",
]
