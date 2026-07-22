"""Thin in-memory order book for ExecutionEngine when OMS is not wired."""

from __future__ import annotations

from domain.entities import Order
from domain.value_objects import CorrelationId, OrderId


class InMemoryOrderStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Order] = {}
        self._by_corr: dict[str, Order] = {}

    def upsert(self, order: Order) -> None:
        self._by_id[order.order_id.value] = order
        self._by_corr[str(order.correlation_id.value)] = order

    def get(self, order_id: OrderId) -> Order | None:
        return self._by_id.get(order_id.value)

    def get_by_correlation(self, correlation_id: CorrelationId) -> Order | None:
        return self._by_corr.get(str(correlation_id.value))

    def all_orders(self) -> list[Order]:
        return list(self._by_id.values())
