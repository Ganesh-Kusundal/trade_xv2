"""Paper portfolio — positions + cash from connection state."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from domain.entities import Account, Position
from domain.value_objects import Money

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperPortfolioAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection

    def get_positions(self) -> list[Position]:
        return list(self._conn.positions.values())

    def get_funds(self) -> Account:
        cash = self._conn.cash
        mtm = Decimal("0")
        for pos in self._conn.positions.values():
            quote = self._conn.quotes.get(pos.instrument_id)
            if quote is None:
                mark = pos.avg_price.value
            else:
                mark = (quote.bid.value + quote.ask.value) / Decimal("2")
            mtm += mark * pos.quantity.value
        equity = Money(amount=cash.amount + mtm, currency=cash.currency)
        return Account(
            account_id=self._conn.account_id(),
            balance=cash,
            margin=Money(amount=Decimal("0"), currency=cash.currency),
            equity=equity,
        )
