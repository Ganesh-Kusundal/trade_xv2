"""Tests for the exchange plugin registry and NSE plugin (P5-2 / G3).

Verifies:
- NseExchangeAdapter satisfies the ExchangeAdapter protocol.
- NseTradingCalendar satisfies the TradingCalendar protocol.
- ExchangeNotConfigured is raised when no adapter is registered.
- After setting adapter, the active adapter is NSE with correct conventions.
"""

from __future__ import annotations

from datetime import date

import pytest

from datalake import exchange_registry
from datalake.exchange_registry import (
    get_active_adapter,
    get_active_exchange_code,
    set_active_adapter,
)
from domain.exceptions import ExchangeNotConfigured
from domain.ports.exchange_adapter import ExchangeAdapter
from domain.ports.exchange_calendar import TradingCalendar
from plugins.exchanges.nse import ADAPTER, CALENDAR


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure each test starts with a clean registry."""
    exchange_registry._active_adapter = None
    exchange_registry._discovered = False
    yield
    exchange_registry._active_adapter = None
    exchange_registry._discovered = False


class TestNsePluginProtocol:
    """NSE plugin satisfies domain port protocols."""

    def test_adapter_satisfies_protocol(self):
        assert isinstance(ADAPTER, ExchangeAdapter)
        assert ADAPTER.exchange == "NSE"
        assert ADAPTER.timezone == "Asia/Kolkata"
        assert ADAPTER.base_currency == "INR"
        assert ADAPTER.price_scale == 100
        assert ADAPTER.normalize_symbol("  reliance  ", "NSE") == "RELIANCE"

    def test_calendar_satisfies_protocol(self):
        assert isinstance(CALENDAR, TradingCalendar)
        assert CALENDAR.exchange == "NSE"
        assert CALENDAR.is_trading_day(date(2026, 7, 13))  # Monday, not a holiday
        assert not CALENDAR.is_trading_day(date(2026, 7, 12))  # Sunday
        bounds = CALENDAR.session_bounds(date(2026, 7, 13))
        assert bounds[0].hour == 9 and bounds[0].minute == 15
        assert bounds[1].hour == 15 and bounds[1].minute == 30
        assert CALENDAR.expected_bars(date(2026, 7, 13), bar_seconds=60) == 375  # 6h15m = 375 min


class TestExchangeRegistry:
    """Registry behavior: discovery, fallback, error."""

    def test_no_adapter_raises(self):
        with pytest.raises(ExchangeNotConfigured):
            get_active_adapter()

    def test_no_adapter_code_raises(self):
        with pytest.raises(ExchangeNotConfigured):
            get_active_exchange_code()

    def test_manual_set(self):
        set_active_adapter(ADAPTER)
        assert get_active_exchange_code() == "NSE"

    def test_get_adapter_returns_same(self):
        set_active_adapter(ADAPTER)
        assert get_active_adapter() is ADAPTER
