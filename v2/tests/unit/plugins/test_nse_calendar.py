"""NSE TradingCalendar is_trading_day — weekends off, holidays respected."""

from __future__ import annotations

from datetime import date

from plugins.exchanges.nse.calendar import NSETradingCalendar


def test_weekday_is_trading_day() -> None:
    cal = NSETradingCalendar()
    # 2024-01-15 was a Monday
    assert cal.is_trading_day(date(2024, 1, 15)) is True


def test_saturday_is_not_trading_day() -> None:
    cal = NSETradingCalendar()
    assert cal.is_trading_day(date(2024, 1, 13)) is False


def test_sunday_is_not_trading_day() -> None:
    cal = NSETradingCalendar()
    assert cal.is_trading_day(date(2024, 1, 14)) is False


def test_listed_holiday_is_not_trading_day() -> None:
    cal = NSETradingCalendar(holidays={date(2024, 1, 26)})  # Republic Day
    assert cal.is_trading_day(date(2024, 1, 26)) is False
