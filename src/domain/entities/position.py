"""Position and Holding domain entities — Money/Quantity fields (TOS-P1-004)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from domain.entities._coercion import _as_money, _as_quantity
from domain.enums import ProductType
from domain.primitives import Money, Quantity


@dataclass(slots=True, frozen=True)
class Position:
    """Canonical position — returned by every broker adapter.

    Quantity/price fields are :class:`Quantity` / :class:`Money` (coerced on init).
    """

    symbol: str
    exchange: str
    quantity: Quantity = Quantity(0)
    avg_price: Money = Money(0)
    ltp: Money = Money(0)
    unrealized_pnl: Money = Money(0)
    realized_pnl: Money = Money(0)
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None
    instrument_id: str | None = None
    multiplier: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _as_quantity(self.quantity))
        object.__setattr__(self, "avg_price", _as_money(self.avg_price))
        object.__setattr__(self, "ltp", _as_money(self.ltp))
        object.__setattr__(self, "unrealized_pnl", _as_money(self.unrealized_pnl))
        object.__setattr__(self, "realized_pnl", _as_money(self.realized_pnl))
        if not isinstance(self.multiplier, Decimal):
            object.__setattr__(self, "multiplier", Decimal(str(self.multiplier)))

    def _mult(self) -> Decimal:
        m = self.multiplier if self.multiplier > 0 else Decimal("1")
        return m

    @property
    def avg_price_money(self) -> Money:
        return self.avg_price

    @property
    def quantity_vo(self) -> Quantity:
        return self.quantity

    @property
    def pnl(self) -> Decimal:
        m = self._mult()
        qty = int(self.quantity)
        avg = self.avg_price.to_decimal()
        ltp = self.ltp.to_decimal()
        if qty > 0:
            return Decimal(str(qty)) * (ltp - avg) * m
        if qty < 0:
            return Decimal(str(abs(qty))) * (avg - ltp) * m
        return Decimal("0")

    def with_ltp(self, ltp: Money | Decimal) -> Position:
        m = self._mult()
        ltp_m = _as_money(ltp)
        qty = int(self.quantity)
        unrealized = (
            Decimal(str(qty)) * (ltp_m.to_decimal() - self.avg_price.to_decimal()) * m
            if qty != 0
            else Decimal("0")
        )
        return replace(self, ltp=ltp_m, unrealized_pnl=_as_money(unrealized))

    def with_fill(
        self,
        quantity: Quantity | int,
        price: Money | Decimal,
    ) -> Position:
        """Return a new Position after applying a signed fill (qty int or Quantity)."""
        fill_qty = int(_as_quantity(quantity))
        fill_price = _as_money(price).to_decimal()
        cur_qty = int(self.quantity)
        new_qty = cur_qty + fill_qty
        new_avg = self._compute_avg_price(new_qty, fill_qty, fill_price)
        new_realized = self._compute_realized_pnl(fill_qty, fill_price)
        new_unrealized = self._compute_unrealized(new_qty, fill_price, new_avg)
        return replace(
            self,
            quantity=Quantity(new_qty),
            avg_price=Money(new_avg),
            ltp=Money(fill_price),
            unrealized_pnl=Money(new_unrealized),
            realized_pnl=Money(new_realized),
        )

    def _compute_avg_price(self, new_qty: int, fill_qty: int, fill_price: Decimal) -> Decimal:
        cur_qty = int(self.quantity)
        avg = self.avg_price.to_decimal()
        if cur_qty == 0:
            return fill_price
        is_closing = (cur_qty > 0 and fill_qty < 0) or (cur_qty < 0 and fill_qty > 0)
        if is_closing:
            if new_qty == 0:
                return Decimal("0")
            if abs(fill_qty) > abs(cur_qty):
                return fill_price
            return avg
        return (
            Decimal(str(cur_qty)) * avg + Decimal(str(fill_qty)) * fill_price
        ) / Decimal(str(new_qty))

    def _compute_realized_pnl(self, fill_qty: int, fill_price: Decimal) -> Decimal:
        cur_qty = int(self.quantity)
        realized = self.realized_pnl.to_decimal()
        avg = self.avg_price.to_decimal()
        if cur_qty == 0:
            return realized
        is_closing = (cur_qty > 0 and fill_qty < 0) or (cur_qty < 0 and fill_qty > 0)
        if not is_closing:
            return realized
        closed = min(abs(cur_qty), abs(fill_qty))
        pnl_factor = Decimal("1") if cur_qty > 0 else Decimal("-1")
        m = self._mult()
        return realized + Decimal(str(closed)) * (fill_price - avg) * pnl_factor * m

    def _compute_unrealized(self, new_qty: int, price: Decimal, avg_price: Decimal) -> Decimal:
        if new_qty == 0:
            return Decimal("0")
        return Decimal(str(new_qty)) * (price - avg_price) * self._mult()


@dataclass(slots=True, frozen=True)
class Holding:
    """Canonical holding — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: Quantity = Quantity(0)
    available_quantity: Quantity = Quantity(0)
    avg_price: Money = Money(0)
    ltp: Money = Money(0)
    pnl: Money = Money(0)
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _as_quantity(self.quantity))
        object.__setattr__(
            self, "available_quantity", _as_quantity(self.available_quantity)
        )
        object.__setattr__(self, "avg_price", _as_money(self.avg_price))
        object.__setattr__(self, "ltp", _as_money(self.ltp))
        object.__setattr__(self, "pnl", _as_money(self.pnl))


class PositionState(str, Enum):
    """Position lifecycle states."""

    FLAT = "FLAT"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSED = "CLOSED"
    REVERSED = "REVERSED"

    @property
    def is_active(self) -> bool:
        return self in (PositionState.OPEN, PositionState.REDUCING, PositionState.REVERSED)

    @property
    def is_terminal(self) -> bool:
        return self in (PositionState.FLAT, PositionState.CLOSED)


POSITION_STATE_TRANSITIONS: dict[PositionState, frozenset[PositionState]] = {
    PositionState.FLAT: frozenset({PositionState.OPEN, PositionState.REVERSED}),
    PositionState.OPEN: frozenset(
        {
            PositionState.OPEN,
            PositionState.REDUCING,
            PositionState.CLOSED,
            PositionState.REVERSED,
        }
    ),
    PositionState.REDUCING: frozenset(
        {
            PositionState.FLAT,
            PositionState.OPEN,
            PositionState.REVERSED,
            PositionState.CLOSED,
        }
    ),
    PositionState.CLOSED: frozenset({PositionState.FLAT}),
    PositionState.REVERSED: frozenset(
        {
            PositionState.FLAT,
            PositionState.OPEN,
            PositionState.REDUCING,
            PositionState.CLOSED,
        }
    ),
}
