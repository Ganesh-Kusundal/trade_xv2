"""ExchangeAdapter — pure domain port for exchange-specific conventions.

ADR-005. Carries the market conventions the datalake currently hardcodes
(NSE session hours, ``"NSE"`` exchange literals, paise/rupee scaling, tick and
lot sizes). Exchange plugins implement this port; the datalake reads conventions
ONLY through the active adapter, never from a hardcoded constant.

This is a pure domain port: no broker logic, no implementation, no imports from
``infrastructure`` or ``brokers``.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Exchange-specific conventions, decoupled from any one market."""

    @property
    def exchange(self) -> str:
        """Canonical exchange code (e.g. ``"NSE"``)."""
        ...

    @property
    def timezone(self) -> str:
        """IANA timezone name for the exchange's local session."""
        ...

    @property
    def base_currency(self) -> str:
        """ISO currency of quoted prices (e.g. ``"INR"``)."""
        ...

    @property
    def price_scale(self) -> int:
        """Multiplier from the exchange's integer price unit to major units.

        E.g. ``100`` means a wire price of 12345 represents 123.45 in
        ``base_currency``. Datalake must use this instead of a ``"paise"``
        literal.
        """
        ...

    @property
    def tick_size(self) -> float:
        """Minimum price increment in ``base_currency``."""
        ...

    @property
    def lot_size(self) -> int:
        """Standard contract lot size for the exchange's F&O segment."""
        ...

    def normalize_symbol(self, symbol: str, exchange: str) -> str:
        """Return the canonical ``(symbol, exchange)``-keyed identifier.

        Centralizes the symbol/exchange naming rules the datalake currently
        bakes in, so no ``"NSE"`` literal leaks into data code.
        """
        ...


@runtime_checkable
class ExchangeAdapterPort(Protocol):
    """Protocol for exchange-specific behavior (trading hours/days)."""

    @property
    def exchange_code(self) -> str:
        """Exchange identifier (e.g., 'NSE', 'BSE', 'MCX')."""
        ...

    @property
    def timezone(self) -> ZoneInfo:
        """Exchange local timezone."""
        ...

    def is_trading_hours(self, now: datetime) -> bool:
        """Check if *now* falls within regular trading hours."""
        ...

    def is_trading_day(self, now: datetime) -> bool:
        """Check if *now*'s date is a trading day."""
        ...


class NSEExchangeAdapter:
    """NSE (National Stock Exchange of India) adapter."""

    exchange_code = "NSE"
    timezone = ZoneInfo("Asia/Kolkata")

    _OPEN = time(9, 15)
    _CLOSE = time(15, 30)

    def is_trading_hours(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        t = local.time()
        return self._OPEN <= t <= self._CLOSE

    def is_trading_day(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        return local.weekday() < 5  # Mon-Fri


class BSEExchangeAdapter:
    """BSE (Bombay Stock Exchange) adapter."""

    exchange_code = "BSE"
    timezone = ZoneInfo("Asia/Kolkata")

    _OPEN = time(9, 15)
    _CLOSE = time(15, 30)

    def is_trading_hours(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        t = local.time()
        return self._OPEN <= t <= self._CLOSE

    def is_trading_day(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        return local.weekday() < 5


class MCXExchangeAdapter:
    """MCX (Multi Commodity Exchange) adapter."""

    exchange_code = "MCX"
    timezone = ZoneInfo("Asia/Kolkata")

    _OPEN = time(9, 0)
    _CLOSE = time(23, 30)

    def is_trading_hours(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        t = local.time()
        return self._OPEN <= t <= self._CLOSE

    def is_trading_day(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        return local.weekday() < 5


_EXCHANGE_REGISTRY: dict[str, type] = {
    "NSE": NSEExchangeAdapter,
    "BSE": BSEExchangeAdapter,
    "MCX": MCXExchangeAdapter,
}


def get_exchange_adapter(exchange: str) -> ExchangeAdapterPort:
    """Get the adapter for *exchange*, raising KeyError if unknown."""
    cls = _EXCHANGE_REGISTRY.get(exchange.upper())
    if cls is None:
        raise KeyError(f"Unknown exchange: {exchange}")
    return cls()
