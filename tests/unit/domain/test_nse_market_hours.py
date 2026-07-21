"""is_nse_market_open — domain market-hours helper used by paper fill gating."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from domain.market.hours import is_nse_market_open

_IST = timezone(timedelta(hours=5, minutes=30))


def test_weekday_open() -> None:
    # 2026-07-20 was a Monday
    assert is_nse_market_open(datetime(2026, 7, 20, 10, 0, tzinfo=_IST)) is True


def test_weekday_closed() -> None:
    assert is_nse_market_open(datetime(2026, 7, 20, 16, 0, tzinfo=_IST)) is False


def test_weekend_closed() -> None:
    assert is_nse_market_open(datetime(2026, 7, 19, 12, 0, tzinfo=_IST)) is False


def test_force_open(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_MARKET_OPEN", "1")
    assert is_nse_market_open(datetime(2026, 7, 19, 3, 0, tzinfo=_IST)) is True
