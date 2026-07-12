"""Exchange port contracts (ADR-005).

Pins the stable contracts that P5-2 depends on: ``TradingCalendar`` and
``ExchangeAdapter`` are pure domain ports, and ``ExchangeNotConfigured`` is the
error callers raise instead of defaulting to ``"NSE"``.
"""

from __future__ import annotations

from datetime import date, time

from domain.exceptions import ExchangeNotConfigured
from domain.ports import ExchangeAdapter, TradingCalendar


class _StubCalendar:
    exchange = "NSE"
    timezone = "Asia/Kolkata"

    def is_trading_day(self, on: date) -> bool:
        return on.weekday() < 5

    def session_bounds(self, on: date) -> tuple[time, time]:
        return time(9, 15), time(15, 30)

    def expected_bars(self, on: date, bar_seconds: int) -> int:
        return 375 if bar_seconds == 60 else 0


class _StubAdapter:
    exchange = "NSE"
    timezone = "Asia/Kolkata"
    base_currency = "INR"
    price_scale = 100
    tick_size = 0.05
    lot_size = 50

    def normalize_symbol(self, symbol: str, exchange: str) -> str:
        return f"{exchange}:{symbol}"


def test_trading_calendar_port_satisfied_structurally() -> None:
    assert isinstance(_StubCalendar(), TradingCalendar)


def test_exchange_adapter_port_satisfied_structurally() -> None:
    assert isinstance(_StubAdapter(), ExchangeAdapter)


def test_exchange_not_configured_is_a_data_error() -> None:
    err = ExchangeNotConfigured("nse not registered")
    assert isinstance(err, Exception)
    assert err.args[0] == "nse not registered"
