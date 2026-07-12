"""TradingCache — single in-memory source of truth for trading state.

Wraps the order/position/quote storage currently scattered across
OrderManager, PositionManager, and broker services. Provides a
unified API for ExecutionEngine, Risk, and strategies.
"""
from __future__ import annotations

import threading
from typing import Any

from domain import Order
from domain.enums import OrderStatus


class TradingCache:
    """Thread-safe in-memory cache for trading state.

    Key-value store for orders, positions, and quotes. All mutations
    go through FSM-validated paths where applicable.
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._orders_by_correlation: dict[str, str] = {}
        self._positions: dict[str, Any] = {}
        self._quotes: dict[str, Any] = {}
        self._lock = threading.RLock()

    # -- Orders --

    def upsert_order(self, order: Order) -> None:
        with self._lock:
            self._orders[order.order_id] = order
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = order.order_id

    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)

    def get_order_by_correlation(self, correlation_id: str) -> Order | None:
        with self._lock:
            order_id = self._orders_by_correlation.get(correlation_id)
            if order_id is None:
                return None
            return self._orders.get(order_id)

    def update_order_status(self, order_id: str, status: OrderStatus) -> Order | None:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                return None
            updated = order.with_status(status)
            self._orders[order_id] = updated
            return updated

    def remove_order(self, order_id: str) -> Order | None:
        with self._lock:
            order = self._orders.pop(order_id, None)
            if order and order.correlation_id:
                self._orders_by_correlation.pop(order.correlation_id, None)
            return order

    def all_orders(self) -> list[Order]:
        with self._lock:
            return list(self._orders.values())

    # -- Positions --

    def upsert_position(self, key: str, position: Any) -> None:
        with self._lock:
            self._positions[key] = position

    def get_position(self, key: str) -> Any | None:
        with self._lock:
            return self._positions.get(key)

    def all_positions(self) -> list[Any]:
        with self._lock:
            return list(self._positions.values())

    # -- Quotes --

    def set_quote(self, instrument_id: str, quote: Any) -> None:
        with self._lock:
            self._quotes[instrument_id] = quote

    def get_quote(self, instrument_id: str) -> Any | None:
        with self._lock:
            return self._quotes.get(instrument_id)

    def clear(self) -> None:
        with self._lock:
            self._orders.clear()
            self._orders_by_correlation.clear()
            self._positions.clear()
            self._quotes.clear()
