"""PositionManager — projects fills into Position qty/avg/realized_pnl."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from application.oms.trading_cache import TradingCache
from domain.entities import Position, Trade
from domain.enums import OrderSide
from domain.value_objects import Money, Price, Quantity

_CURRENCY = "INR"


class PositionManager:
    def __init__(self, cache: TradingCache) -> None:
        self._cache = cache

    def apply_trade(self, trade: Trade) -> Position:
        existing = self._cache.get_position(trade.instrument_id)
        if existing is None:
            pos = Position(
                instrument_id=trade.instrument_id,
                quantity=Quantity(value=Decimal("0")),
                avg_price=Price(value=Decimal("0")),
                realized_pnl=Money(amount=Decimal("0"), currency=_CURRENCY),
                unrealized_pnl=Money(amount=Decimal("0"), currency=_CURRENCY),
            )
        else:
            pos = existing

        signed = trade.quantity.value if trade.side is OrderSide.BUY else -trade.quantity.value
        old_qty = pos.quantity.value
        new_qty = old_qty + signed

        if old_qty == 0 or (old_qty > 0 and signed > 0) or (old_qty < 0 and signed < 0):
            # opening / increasing same side — weighted average
            if new_qty == 0:
                avg = Decimal("0")
            else:
                abs_old = abs(old_qty)
                abs_new = abs(new_qty)
                avg = (
                    (pos.avg_price.value * abs_old) + (trade.price.value * abs(signed))
                ) / abs_new
            realized = pos.realized_pnl
        else:
            # reducing / flipping — realize PnL on closed qty
            closed = min(abs(old_qty), abs(signed))
            if old_qty > 0:
                pnl = (trade.price.value - pos.avg_price.value) * closed
            else:
                pnl = (pos.avg_price.value - trade.price.value) * closed
            realized = Money(
                amount=pos.realized_pnl.amount + pnl,
                currency=pos.realized_pnl.currency,
            )
            if new_qty == 0:
                avg = Decimal("0")
            elif (old_qty > 0) != (new_qty > 0):
                # flipped — leftover opens at trade price
                avg = trade.price.value
            else:
                avg = pos.avg_price.value

        pos = replace(
            pos,
            quantity=Quantity(value=new_qty),
            avg_price=Price(value=avg),
            realized_pnl=realized,
        )
        self._cache.set_position(pos)
        return pos
