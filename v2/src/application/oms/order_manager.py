"""OrderManager — orchestrates Order FSM; stores results in TradingCache."""

from __future__ import annotations

from dataclasses import replace

from application.oms.trading_cache import TradingCache
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


class OrderManager:
    def __init__(self, cache: TradingCache) -> None:
        self._cache = cache

    def create_pending(
        self,
        *,
        order_id: OrderId,
        instrument_id: InstrumentId,
        side: OrderSide,
        order_type: OrderType,
        quantity: Quantity,
        price: Price | None,
        time_in_force: TimeInForce,
        correlation_id: CorrelationId,
    ) -> Order:
        order = Order(
            order_id=order_id,
            instrument_id=instrument_id,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            status=OrderStatus.PENDING,
            correlation_id=correlation_id,
        )
        self._cache.set_order(order)
        return order

    def upsert(self, order: Order) -> None:
        self._cache.set_order(order)

    def get_order(self, order_id: OrderId) -> Order:
        order = self._cache.get_order(order_id)
        if order is None:
            raise KeyError(f"order not found: {order_id.value}")
        return order

    def apply_submitted(self, order_id: OrderId) -> Order:
        return self._transition(order_id, OrderStatus.SUBMITTED)

    def apply_fill(self, order_id: OrderId, filled_qty: Quantity) -> Order:
        order = self.get_order(order_id)
        new_filled = Quantity(value=order.filled_quantity.value + filled_qty.value)
        if new_filled.value > order.quantity.value:
            raise ValueError(
                f"fill qty {new_filled.value} exceeds order qty {order.quantity.value}"
            )
        target = (
            OrderStatus.FILLED
            if new_filled.value == order.quantity.value
            else OrderStatus.PARTIALLY_FILLED
        )
        order = order.transition_to(target)
        order = replace(order, filled_quantity=new_filled)
        self._cache.set_order(order)
        return order

    def apply_cancel(self, order_id: OrderId) -> Order:
        return self._transition(order_id, OrderStatus.CANCELLED)

    def apply_reject(self, order_id: OrderId) -> Order:
        return self._transition(order_id, OrderStatus.REJECTED)

    def apply_unknown(self, order_id: OrderId) -> Order:
        return self._transition(order_id, OrderStatus.UNKNOWN)

    def _transition(self, order_id: OrderId, status: OrderStatus) -> Order:
        order = self.get_order(order_id)
        order = order.transition_to(status)
        self._cache.set_order(order)
        return order
