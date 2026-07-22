"""Authoritative in-memory trading state (orders, positions, quotes)."""

from __future__ import annotations

from domain.entities import Order, Position, Quote
from domain.value_objects import InstrumentId, OrderId


class TradingCache:
    """ponytail: plain dicts; ceiling = single-threaded engine. Upgrade: lock/sharding."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._quotes: dict[str, Quote] = {}

    def set_order(self, order: Order) -> None:
        self._orders[order.order_id.value] = order

    def get_order(self, order_id: OrderId | str) -> Order | None:
        key = order_id.value if isinstance(order_id, OrderId) else order_id
        return self._orders.get(key)

    def set_position(self, position: Position) -> None:
        self._positions[position.instrument_id.value] = position

    def get_position(self, instrument_id: InstrumentId | str) -> Position | None:
        key = instrument_id.value if isinstance(instrument_id, InstrumentId) else instrument_id
        return self._positions.get(key)

    def set_quote(self, quote: Quote) -> None:
        self._quotes[quote.instrument_id.value] = quote

    def get_quote(self, instrument_id: InstrumentId | str) -> Quote | None:
        key = instrument_id.value if isinstance(instrument_id, InstrumentId) else instrument_id
        return self._quotes.get(key)

    def snapshot(self) -> dict[str, dict]:
        return {
            "orders": dict(self._orders),
            "positions": dict(self._positions),
            "quotes": dict(self._quotes),
        }
