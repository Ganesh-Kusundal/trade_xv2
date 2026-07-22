"""Tests for the MCX exchange plugin (ADR-005 / tradex.exchanges)."""

from __future__ import annotations

from datetime import date, time

from domain.ports.exchange_adapter import ExchangeAdapter
from domain.ports.exchange_calendar import TradingCalendar
from plugins.exchanges.mcx import ADAPTER, CALENDAR


class TestMcxPluginProtocol:
    """MCX plugin satisfies domain port protocols."""

    def test_adapter_satisfies_protocol(self) -> None:
        assert isinstance(ADAPTER, ExchangeAdapter)
        assert ADAPTER.exchange == "MCX"
        assert ADAPTER.timezone == "Asia/Kolkata"
        assert ADAPTER.base_currency == "INR"
        assert ADAPTER.price_scale == 100
        assert ADAPTER.normalize_symbol("  crudeoil  ", "MCX") == "CRUDEOIL"

    def test_calendar_satisfies_protocol(self) -> None:
        assert isinstance(CALENDAR, TradingCalendar)
        assert CALENDAR.exchange == "MCX"
        assert CALENDAR.timezone == "Asia/Kolkata"

    def test_weekday_is_trading_day(self) -> None:
        assert CALENDAR.is_trading_day(date(2026, 7, 13))  # Monday

    def test_weekend_is_not_trading_day(self) -> None:
        assert not CALENDAR.is_trading_day(date(2026, 7, 12))  # Sunday

    def test_session_bounds(self) -> None:
        bounds = CALENDAR.session_bounds(date(2026, 7, 13))
        assert bounds == (time(9, 0), time(23, 30))

    def test_expected_bars_one_minute(self) -> None:
        # 09:00–23:30 = 14h30m = 870 minutes
        assert CALENDAR.expected_bars(date(2026, 7, 13), bar_seconds=60) == 870

    def test_expected_bars_zero_on_weekend(self) -> None:
        assert CALENDAR.expected_bars(date(2026, 7, 12), bar_seconds=60) == 0
