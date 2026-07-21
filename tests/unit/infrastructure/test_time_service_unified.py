"""Tests for the unified infrastructure.time_service (REF-7 merge).

Proves the merged TimeService supports both:
- DI injection via FakeClock / with_clock()
- Exchange calendar integration from the infrastructure layer
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from infrastructure.time_service import (
    FakeClock,
    SystemClock,
    TimeService,
    _wrap,
)


class TestUnifiedTimeServiceNow:
    def test_now_returns_utc_datetime(self):
        ts = TimeService()
        now = ts.now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_now_utc_alias(self):
        fixed = datetime(2024, 6, 15, tzinfo=timezone.utc)
        ts = TimeService.with_clock(FakeClock(initial=fixed))
        assert ts.now() == ts.now_utc() == fixed


class TestFakeClock:
    def test_set_and_advance(self):
        fc = FakeClock(initial=datetime(2023, 6, 1, tzinfo=timezone.utc))
        assert fc.now() == datetime(2023, 6, 1, tzinfo=timezone.utc)

        fc.advance(timedelta(hours=2))
        assert fc.now() == datetime(2023, 6, 1, 2, tzinfo=timezone.utc)

        fc.set(datetime(2024, 12, 25, tzinfo=timezone.utc))
        assert fc.now() == datetime(2024, 12, 25, tzinfo=timezone.utc)

    def test_naive_initial_becomes_utc(self):
        fc = FakeClock(initial=datetime(2020, 7, 4))
        assert fc.now().tzinfo == timezone.utc

    def test_current_property(self):
        fc = FakeClock()
        assert fc.current == fc.now()


class TestWithClockInjection:
    def test_with_fake_clock(self):
        fixed = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        fc = FakeClock(initial=fixed)
        ts = TimeService.with_clock(fc)
        assert ts.now() == fixed

        fc.advance(timedelta(minutes=30))
        assert ts.now() == fixed + timedelta(minutes=30)

    def test_with_bare_callable(self):
        sentinel = datetime(2021, 3, 1, tzinfo=timezone.utc)
        ts = TimeService.with_clock(lambda: sentinel)
        assert ts.now() is sentinel

    def test_with_clock_value_object(self):
        from domain.primitives.value_objects import Clock

        sentinel = datetime(2022, 8, 8, tzinfo=timezone.utc)
        clock = Clock(_now=lambda: sentinel)
        ts = TimeService.with_clock(clock)
        assert ts.now() == sentinel

    def test_exchange_now_still_works_with_injected_clock(self):
        fc = FakeClock(initial=datetime(2024, 6, 15, tzinfo=timezone.utc))
        ts = TimeService.with_clock(fc)
        nse = ts.exchange_now("NSE")
        assert nse.tzinfo is not None


class TestWrapHelper:
    def test_wrap_none_returns_system_clock(self):
        clock = _wrap(None)
        now = clock.now()
        assert now.tzinfo == timezone.utc

    def test_wrap_clock_passthrough(self):
        from domain.primitives.value_objects import Clock

        sentinel = datetime(2020, 1, 1, tzinfo=timezone.utc)
        c = Clock(_now=lambda: sentinel)
        assert _wrap(c) is c

    def test_wrap_fake_clock(self):
        fc = FakeClock(initial=datetime(2019, 5, 5, tzinfo=timezone.utc))
        clock = _wrap(fc)
        assert clock.now() == datetime(2019, 5, 5, tzinfo=timezone.utc)
