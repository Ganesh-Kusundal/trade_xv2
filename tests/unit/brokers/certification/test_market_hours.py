"""Market-hours IST phase detection unit tests."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from brokers.certification.market_hours import MarketPhase, current_phase, is_nse_market_open

_IST = timezone(timedelta(hours=5, minutes=30))


@pytest.mark.unit
@pytest.mark.certification
def test_weekend_phase() -> None:
    # Saturday 2026-07-11 is a Saturday
    sat = datetime(2026, 7, 11, 12, 0, tzinfo=_IST)
    assert current_phase(sat) == MarketPhase.WEEKEND.value


@pytest.mark.unit
@pytest.mark.certification
def test_market_hours_phase() -> None:
    # Monday 2026-07-13 10:00 IST
    mon = datetime(2026, 7, 13, 10, 0, tzinfo=_IST)
    assert current_phase(mon) == MarketPhase.MARKET_HOURS.value


@pytest.mark.unit
@pytest.mark.certification
def test_pre_market_phase() -> None:
    mon = datetime(2026, 7, 13, 9, 5, tzinfo=_IST)
    assert current_phase(mon) == MarketPhase.PRE_MARKET.value


@pytest.mark.unit
@pytest.mark.certification
def test_is_nse_market_open_only_during_session() -> None:
    mon_open = datetime(2026, 7, 13, 10, 0, tzinfo=_IST)
    mon_closed = datetime(2026, 7, 13, 18, 0, tzinfo=_IST)
    assert is_nse_market_open(mon_open) is True
    assert is_nse_market_open(mon_closed) is False
