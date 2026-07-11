"""Financial value objects — Money and TickSize.

``Money`` is the canonical type from ``domain.primitives`` (TOS-P1-003).
This module re-exports it and keeps ``TickSize`` / ``MoneyField`` for API schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import PlainSerializer

from domain.primitives.value_objects import Money  # canonical SSOT

# Pydantic-compatible type alias: Decimal internally, float in JSON.
MoneyField = Annotated[Decimal, PlainSerializer(float, return_type=float)]


@dataclass(frozen=True, slots=True)
class TickSize:
    """Minimum price increment for an instrument."""

    value: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            object.__setattr__(self, "value", Decimal(str(self.value)))
        if self.value <= 0:
            raise ValueError(f"tick size must be positive, got {self.value}")

    def snap(self, price: Decimal | Money) -> Decimal:
        """Snap *price* to the nearest tick (half-up)."""
        if isinstance(price, Money):
            price = price.to_decimal()
        elif not isinstance(price, Decimal):
            price = Decimal(str(price))
        ticks = (price / self.value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return ticks * self.value

    def is_valid_price(self, price: Decimal | Money | float | int | str) -> bool:
        """True if *price* is an integer multiple of this tick."""
        if isinstance(price, Money):
            price = price.to_decimal()
        else:
            price = Decimal(str(price))
        if self.value == 0:
            return False
        q = price / self.value
        return q == q.to_integral_value()


__all__ = ["Money", "MoneyField", "TickSize"]
