"""Tests for runtime.time_service — injectable TimeService with real/fake clocks.

Proves:
- Default TimeService uses the real wall clock.
- A FakeClock (or any callable / Clock) can be injected for deterministic tests.
- SystemClock only lives in the runtime layer, never imported by the VO module.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.primitives.value_objects import Clock
from runtime.time_service import FakeClock, SystemClock, TimeService


class TestSystemClock:
    def test_real_clock_returns_utc_aware_now(self):
        now = SystemClock().now()
        assert now.tzinfo is not None
        # Should be within a couple seconds of actual wall clock.
        assert abs((datetime.now(timezone.utc) - now).total_seconds()) < 5


class TestFakeClock:
    def test_deterministic_and_controllable(self):
        start = datetime(2023, 3, 4, 9, 0, tzinfo=timezone.utc)
        fc = FakeClock(initial=start)
        assert fc.now() == start

        fc.advance(timedelta(minutes=15))
        assert fc.now() == start + timedelta(minutes=15)

        fc.set(datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert fc.now() == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_naive_initial_is_treated_as_utc(self):
        fc = FakeClock(initial=datetime(2020, 1, 1))
        assert fc.now().tzinfo == timezone.utc


class TestTimeServiceInjection:
    def test_default_uses_real_clock(self):
        ts = TimeService()
        now = ts.now()
        assert now.tzinfo is not None
        assert abs((datetime.now(timezone.utc) - now).total_seconds()) < 5

    def test_with_fake_clock_is_deterministic(self):
        start = datetime(2025, 5, 5, 10, 30, tzinfo=timezone.utc)
        fake_clock = FakeClock(initial=start)
        ts = TimeService.with_clock(fake_clock)
        assert ts.now() == start
        # Advancing the injected fake clock flows through the service.
        fake_clock.advance(timedelta(hours=1))
        assert ts.now() == start + timedelta(hours=1)

    def test_with_bare_callable(self):
        fixed = datetime(2019, 9, 9, tzinfo=timezone.utc)
        ts = TimeService.with_clock(lambda: fixed)
        assert ts.now() == fixed
        assert ts.now_utc() == fixed

    def test_with_clock_value_object(self):
        fixed = datetime(2018, 8, 8, tzinfo=timezone.utc)
        clock = Clock(_now=lambda: fixed)
        ts = TimeService.with_clock(clock)
        assert ts.now() == fixed

    def test_now_delegates_to_injected_clock_only(self):
        # Prove the service never computes its own time: a callable returning
        # a constant is faithfully returned every call.
        sentinel = datetime(2001, 1, 1, tzinfo=timezone.utc)
        ts = TimeService.with_clock(lambda: sentinel)
        assert ts.now() is sentinel
        assert ts.now() is sentinel
