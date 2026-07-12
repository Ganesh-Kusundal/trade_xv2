"""Clock contract — guarantees for ClockPort, RealClock, VirtualClock.

These tests pin the shared time seam that Virtual Clock (Tier 1-A) and
deterministic replay/testing build on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.events.types import DomainEvent
from domain.ports.time_service import (
    ClockPort,
    RealClock,
    VirtualClock,
    get_current_clock,
    set_current_clock,
    use_clock,
)


def test_real_clock_returns_timezone_aware_utc() -> None:
    now = RealClock().now()
    assert now.tzinfo == timezone.utc


def test_real_clock_satisfies_clock_port() -> None:
    assert isinstance(RealClock(), ClockPort)


def test_virtual_clock_is_deterministic_and_advances() -> None:
    start = datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc)
    clock = VirtualClock(initial=start)

    assert clock.now() == start
    clock.advance(timedelta(minutes=5))
    assert clock.now() == start + timedelta(minutes=5)
    # Virtual clock is mutable and stable across repeated reads.
    assert clock.now() == start + timedelta(minutes=5)


def test_virtual_clock_set_accepts_naive_as_utc() -> None:
    clock = VirtualClock()
    clock.set(datetime(2026, 3, 4, 10, 0))  # naive
    assert clock.now().tzinfo == timezone.utc
    assert clock.now().hour == 10


def test_use_clock_overrides_domain_event_timestamp() -> None:
    fixed = datetime(2026, 5, 6, 11, 30, tzinfo=timezone.utc)
    with use_clock(VirtualClock(initial=fixed)):
        event = DomainEvent.now("TICK", {"ltp": 100.0})
        assert event.timestamp == fixed
    # Outside the context manager, the default real clock resumes.
    assert isinstance(get_current_clock(), RealClock)


def test_set_current_clock_is_context_scoped() -> None:
    fixed = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    set_current_clock(VirtualClock(initial=fixed))
    try:
        assert DomainEvent.now("QUOTE", {"ltp": 1.0}).timestamp == fixed
    finally:
        set_current_clock(RealClock())


def test_exchange_now_real_clock_uses_exchange_timezone() -> None:
    nse = RealClock().exchange_now("NSE")
    # NSE is Asia/Kolkata (UTC+5:30); the offset from UTC must be 5h30m.
    assert nse.utcoffset() == timedelta(hours=5, minutes=30)
    assert nse.tzinfo is not None


def test_exchange_now_unknown_exchange_falls_back_to_utc() -> None:
    unknown = RealClock().exchange_now("NOT_A_REAL_EXCHANGE")
    assert unknown.utcoffset() == timedelta(0)
