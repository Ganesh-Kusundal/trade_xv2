"""Guarantee: the daily PnL reset scheduler fires based on the virtual clock.

When a ``VirtualClock`` is active, the scheduler's rollover detection and
``last_reset`` bookkeeping must derive from ``get_current_clock()`` rather than
the real wall clock, so resets are deterministic and replayable under tests.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from application.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler
from domain.ports.time_service import get_current_clock, use_clock
from domain.ports.time_service_impls import VirtualClock


class _FakeRiskManager:
    """Records how many times the daily PnL reset was invoked."""

    def __init__(self) -> None:
        self.reset_calls = 0

    def reset_daily_pnl(self) -> None:
        self.reset_calls += 1


def test_daily_pnl_reset_scheduler_fires_at_virtual_time() -> None:
    """A rollover crossing is detected at virtual time, not real wall clock.

    The virtual clock sits just after an IST midnight rollover. The reset must
    fire once and record the *virtual* rollover moment, which differs from what
    the real wall clock would compute today.
    """
    # IST 2026-06-16 00:30 == UTC 2026-06-15 19:00.
    virtual = VirtualClock(initial=datetime(2026, 6, 15, 19, 0, 0, tzinfo=timezone.utc))
    risk = _FakeRiskManager()
    scheduler = DailyPnlResetScheduler(risk, rollover_hour_ist=0, poll_interval_seconds=60)

    with use_clock(virtual):
        # Pretend the last reset happened at the previous IST midnight.
        scheduler._last_reset_unix = scheduler._last_rollover_unix(virtual.timestamp() - 86400.0)
        scheduler._maybe_reset()

    assert risk.reset_calls == 1
    # The recorded reset moment equals the virtual rollover, not the real one.
    virtual_rollover = scheduler._last_rollover_unix(virtual.timestamp())
    assert scheduler._last_reset_unix == virtual_rollover
    real_rollover = scheduler._last_rollover_unix(time.time())
    assert scheduler._last_reset_unix != real_rollover


def test_daily_pnl_reset_scheduler_next_reset_is_virtual() -> None:
    """The next-reset (rollover) computation honours the active virtual clock.

    ``_last_rollover_unix`` returns the IST-midnight boundary at/before the
    supplied time. Fed the virtual clock's timestamp, it must yield the virtual
    boundary, not the one the real wall clock would compute today.
    """
    virtual = VirtualClock(initial=datetime(2026, 6, 15, 19, 0, 0, tzinfo=timezone.utc))
    scheduler = DailyPnlResetScheduler(_FakeRiskManager(), rollover_hour_ist=0)

    with use_clock(virtual):
        next_reset = scheduler._last_rollover_unix(get_current_clock().timestamp())

    expected = datetime(2026, 6, 15, 18, 30, tzinfo=timezone.utc).timestamp()
    assert next_reset == expected
    assert next_reset != scheduler._last_rollover_unix(time.time())
