"""Tests for SystemClock and FakeClock implementations."""

import time
from datetime import timedelta

import pytest

from domain.ports.clock import Clock
from domain.value_objects import Timestamp
from infrastructure.clock import FakeClock, SystemClock


class TestSystemClock:
    def test_now_returns_timestamp(self) -> None:
        clock = SystemClock()
        result = clock.now()
        assert isinstance(result, Timestamp)

    def test_now_returns_nanosecond_precision(self) -> None:
        clock = SystemClock()
        result = clock.now()
        # Timestamp.value should be nanoseconds (19+ digits for current time)
        assert result.value > 1_000_000_000_000_000_000

    def test_now_returns_reasonable_value(self) -> None:
        clock = SystemClock()
        before_ns = time.time_ns()
        result = clock.now()
        after_ns = time.time_ns()
        # Result should be within the measurement window
        assert before_ns <= result.value <= after_ns

    def test_advance_raises_not_implemented_error(self) -> None:
        clock = SystemClock()
        with pytest.raises(NotImplementedError):
            clock.advance(timedelta(seconds=1))


class TestFakeClock:
    def test_starts_at_specified_time(self) -> None:
        start_ns = 1_000_000_000_000_000_000
        clock = FakeClock(start=Timestamp(value=start_ns))
        assert clock.now().value == start_ns

    def test_starts_at_default_time(self) -> None:
        clock = FakeClock()
        # Default should be a reasonable timestamp
        assert clock.now().value > 0

    def test_advance_moves_time_forward(self) -> None:
        clock = FakeClock(start=Timestamp(value=1_000_000_000_000_000_000))
        initial = clock.now().value
        clock.advance(timedelta(seconds=10))
        # 10 seconds = 10_000_000_000 nanoseconds
        assert clock.now().value == initial + 10_000_000_000

    def test_advance_accumulates(self) -> None:
        clock = FakeClock(start=Timestamp(value=1_000_000_000_000_000_000))
        clock.advance(timedelta(seconds=5))
        clock.advance(timedelta(seconds=5))
        # Two advances of 5 seconds = 10 seconds total
        assert clock.now().value == 1_000_000_000_000_000_000 + 10_000_000_000

    def test_satisfies_clock_protocol(self) -> None:
        clock = FakeClock()
        assert isinstance(clock, Clock)


class TestSystemClockProtocol:
    def test_satisfies_clock_protocol(self) -> None:
        clock = SystemClock()
        # SystemClock should satisfy Clock protocol for now() method
        assert hasattr(clock, 'now')
        assert callable(clock.now)
