"""Trade domain entity — Money/Quantity fields (TOS-P1-004)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from domain.primitives import Money, Quantity
from domain.types import ProductType, Side


def _as_money(value: Money | Decimal | int | float | str | None) -> Money:
    if value is None:
        return Money(0)
    if isinstance(value, Money):
        return value
    return Money(value)


def _as_quantity(value: Quantity | Decimal | int | float | str | None) -> Quantity:
    if value is None:
        return Quantity(0)
    if isinstance(value, Quantity):
        return value
    return Quantity(value)


@dataclass(slots=True, frozen=True)
class Trade:
    """Canonical trade — returned by every broker adapter."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: Side
    quantity: Quantity
    price: Money = Money(0)
    trade_value: Money = Money(0)
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _as_quantity(self.quantity))
        object.__setattr__(self, "price", _as_money(self.price))
        object.__setattr__(self, "trade_value", _as_money(self.trade_value))

    @property
    def value(self) -> Decimal:
        if self.trade_value.to_decimal() > 0:
            return self.trade_value.to_decimal()
        return self.price.to_decimal() * Decimal(str(int(self.quantity)))
