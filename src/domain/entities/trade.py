"""Trade domain entity — Money/Quantity fields (TOS-P1-004)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from domain.constants import DEFAULT_EXCHANGE
from domain.entities._coercion import _as_money, _as_quantity
from domain.primitives import Money, Quantity
from domain.types import ProductType, Side


def build_domain_trade(
    *,
    trade_id: str,
    symbol: str,
    side: Side | str,
    quantity: int | Quantity,
    price: Money | Decimal | int | float | str,
    trade_value: Money | Decimal | int | float | str | None = None,
    exchange: str = DEFAULT_EXCHANGE,
    order_id: str = "",
) -> Trade:
    """Shared paper/replay → domain Trade converter (zero-parity helper).

    Analytics ``PaperTrade`` / ``SimulatedTrade`` stay thin session records;
    both call this instead of duplicating Trade construction.
    """
    if isinstance(side, str):
        side = Side.BUY if str(side).upper() == "BUY" else Side.SELL
    tv = trade_value if trade_value is not None else Decimal("0")
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
        trade_value=tv,
    )


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
