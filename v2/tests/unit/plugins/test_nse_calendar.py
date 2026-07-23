"""Tests for NSE trading calendar."""

from datetime import date

from plugins.exchanges.nse.calendar import NSETradingCalendar, NSE_HOLIDAYS


def test_weekends_are_non_trading():
    cal = NSETradingCalendar()
    # Saturday
    assert not cal.is_trading_day(date(2024, 1, 27))
    # Sunday
    assert not cal.is_trading_day(date(2024, 1, 28))


def test_holidays_are_non_trading():
    cal = NSETradingCalendar()
    for holiday in NSE_HOLIDAYS:
        assert not cal.is_trading_day(holiday), f"{holiday} should be a holiday"


def test_weekdays_are_trading_days():
    cal = NSETradingCalendar()
    # A known Monday that's not a holiday
    assert cal.is_trading_day(date(2024, 1, 22))


def test_custom_holidays():
    custom = {date(2024, 6, 15)}
    cal = NSETradingCalendar(holidays=custom)
    assert not cal.is_trading_day(date(2024, 6, 15))
    # Default holidays not included
    assert cal.is_trading_day(date(2024, 1, 26))


def test_2024_key_holidays():
    cal = NSETradingCalendar()
    assert not cal.is_trading_day(date(2024, 1, 26))   # Republic Day
    assert not cal.is_trading_day(date(2024, 3, 29))   # Good Friday
    assert not cal.is_trading_day(date(2024, 8, 15))   # Independence Day
    assert not cal.is_trading_day(date(2024, 10, 12))  # Dussehra
    assert not cal.is_trading_day(date(2024, 11, 1))   # Diwali
    assert not cal.is_trading_day(date(2024, 12, 25))  # Christmas


def test_2025_key_holidays():
    cal = NSETradingCalendar()
    assert not cal.is_trading_day(date(2025, 1, 26))   # Republic Day
    assert not cal.is_trading_day(date(2025, 4, 18))   # Good Friday
    assert not cal.is_trading_day(date(2025, 8, 15))   # Independence Day
    assert not cal.is_trading_day(date(2025, 9, 27))   # Dussehra
    assert not cal.is_trading_day(date(2025, 10, 21))  # Diwali
    assert not cal.is_trading_day(date(2025, 12, 25))  # Christmas
