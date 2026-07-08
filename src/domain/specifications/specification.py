"""Specification ABC — defines the contract for instrument specifications.

A Specification encapsulates the trading rules for an instrument type:
lot size, tick size, margin requirements, trading hours, etc. Different
instrument types (equity, futures, options) provide concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class Specification(ABC):
    """Abstract base for instrument trading specifications."""

    @property
    @abstractmethod
    def instrument_type(self) -> str:
        """Instrument type identifier (EQUITY, FUTURES, OPTIONS, INDEX)."""

    @property
    @abstractmethod
    def lot_size(self) -> int:
        """Minimum tradeable quantity."""

    @property
    @abstractmethod
    def tick_size(self) -> Decimal:
        """Minimum price increment."""

    @property
    def margin_factor(self) -> Decimal:
        """Margin requirement as a fraction of notional. Default 1.0 (full margin)."""
        return Decimal("1.0")

    @property
    def is_tradeable(self) -> bool:
        """Whether instruments of this type can be traded. Default True."""
        return True

    def validate_quantity(self, qty: int) -> bool:
        """Return True if *qty* is a valid multiple of lot_size."""
        if qty < 1:
            return False
        return qty % self.lot_size == 0

    def validate_price(self, price: Decimal) -> bool:
        """Return True if *price* is a valid tick multiple."""
        if price <= 0:
            return False
        remainder = price % self.tick_size
        return remainder == Decimal("0")
