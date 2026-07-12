"""TradingCalendar — pure domain port for exchange trading sessions.

ADR-005. Replaces the hardcoded ``EXCHANGE_CALENDARS`` dict in
``infrastructure/time_service.py``. Exchange plugins implement this port; the
datalake and any session-aware code depend on it instead of assuming NSE/IST.

This is a pure domain port: no broker logic, no implementation, no imports from
``infrastructure`` or ``brokers``.
"""

from __future__ import annotations

from datetime import date, time
from typing import Protocol, runtime_checkable


@runtime_checkable
class TradingCalendar(Protocol):
    """Exchange trading-session calendar.

    Implementations are provided by exchange plugins (entry-point group
    ``tradex.exchanges``). Until an exchange plugin is registered for the
    active exchange, callers must raise ``ExchangeNotConfigured`` rather than
    defaulting to a hardcoded exchange.
    """

    @property
    def exchange(self) -> str:
        """Canonical exchange code (e.g. ``"NSE"``)."""
        ...

    @property
    def timezone(self) -> str:
        """IANA timezone name (e.g. ``"Asia/Kolkata"``)."""
        ...

    def is_trading_day(self, on: date) -> bool:
        """True if ``on`` is a trading session for this exchange."""
        ...

    def session_bounds(self, on: date) -> tuple[time, time]:
        """Regular session open/close local times for ``on``.

        Returns ``(open, close)``. If ``on`` is not a trading day, the
        behavior is implementation-defined (raise or return sentinel).
        """
        ...

    def expected_bars(self, on: date, bar_seconds: int) -> int:
        """Expected number of bars of ``bar_seconds`` length for session ``on``.

        Used by data-quality checks to detect gaps without exchange-specific
        constants living in the datalake.
        """
        ...


__all__ = ["TradingCalendar"]
