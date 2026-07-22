"""MCX ExchangeAdapter — exchange-specific conventions for Multi Commodity Exchange of India.

Implements ``domain.ports.ExchangeAdapter`` (ADR-005). Carries market
conventions the datalake currently hardcodes: exchange code, timezone,
price scaling (paise→INR), and lot/tick sizes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.exchanges.mcx.calendar import McxTradingCalendar


class McxExchangeAdapter:
    """MCX-specific conventions."""

    _calendar: McxTradingCalendar | None = None

    @property
    def exchange(self) -> str:
        return "MCX"

    @property
    def timezone(self) -> str:
        return "Asia/Kolkata"

    @property
    def base_currency(self) -> str:
        return "INR"

    @property
    def price_scale(self) -> int:
        """100 — wire prices are in paise; divide by 100 for INR."""
        return 100

    @property
    def tick_size(self) -> float:
        return 1.0

    @property
    def lot_size(self) -> int:
        return 1

    @property
    def calendar(self) -> McxTradingCalendar:
        """Return the MCX trading calendar (lazy to avoid circular import)."""
        if self._calendar is None:
            from plugins.exchanges.mcx.calendar import McxTradingCalendar

            self._calendar = McxTradingCalendar()
        return self._calendar

    def normalize_symbol(self, symbol: str, exchange: str) -> str:
        """Return the canonical symbol (uppercased, stripped)."""
        return symbol.strip().upper()
