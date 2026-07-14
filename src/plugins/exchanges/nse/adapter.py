"""NSE ExchangeAdapter — exchange-specific conventions for the National Stock Exchange of India.

Implements ``domain.ports.ExchangeAdapter`` (ADR-005). Carries market
conventions the datalake currently hardcodes: exchange code, timezone,
price scaling (paise→INR), and lot/tick sizes.
"""

from __future__ import annotations


class NseExchangeAdapter:
    """NSE-specific conventions."""

    @property
    def exchange(self) -> str:
        return "NSE"

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
        return 0.05

    @property
    def lot_size(self) -> int:
        return 1

    def normalize_symbol(self, symbol: str, exchange: str) -> str:
        """Return the canonical symbol (uppercased, stripped)."""
        return symbol.strip().upper()
