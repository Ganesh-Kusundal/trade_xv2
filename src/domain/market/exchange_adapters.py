"""Concrete exchange adapters — NSE, BSE, MCX.

Moved out of ``domain.ports.exchange_adapter`` to keep ports pure Protocol
definitions. These are behavioural implementations owned by the market domain.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING

from domain.constants.market import IST
from domain.market.hours import NSE_EQUITY_CLOSE, NSE_EQUITY_OPEN

if TYPE_CHECKING:
    from domain.ports.exchange_adapter import ExchangeAdapterPort


class NSEExchangeAdapter:
    """NSE (National Stock Exchange of India) adapter."""

    exchange_code = "NSE"
    timezone = IST

    _OPEN = NSE_EQUITY_OPEN
    _CLOSE = NSE_EQUITY_CLOSE

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
    timezone = IST

    _OPEN = NSE_EQUITY_OPEN
    _CLOSE = NSE_EQUITY_CLOSE

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
    timezone = IST

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
