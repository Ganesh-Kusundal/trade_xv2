"""Dhan order placement / cancel / modify / book."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderStatus
from domain.value_objects import OrderId
from plugins.brokers.dhan.wire import DhanWire

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport


class DhanOrdersAdapter:
    def __init__(self, transport: BaseTransport, wire: DhanWire) -> None:
        self._transport = transport
        self._wire = wire
        self._cache: dict[str, Order] = {}

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        body = self._wire.from_place_command(command)
        ack = self._transport.post("/orders", json=body)
        oid = self._wire.to_order_id(ack)
        order = Order(
            order_id=oid,
            instrument_id=command.instrument_id,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            time_in_force=command.time_in_force,
            status=OrderStatus.PENDING,
            correlation_id=command.correlation_id,
        )
        order.transition_to(OrderStatus.SUBMITTED)
        self._cache[oid.value] = order
        return oid

    def cancel_order(self, order_id: OrderId) -> None:
        self._transport.post(f"/orders/{order_id.value}/cancel", json={})
        cached = self._cache.get(order_id.value)
        if cached is not None and cached.status not in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        ):
            cached.transition_to(OrderStatus.CANCELLED)

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        body = self._wire.from_place_command(command)
        self._transport.post(f"/orders/{order_id.value}", json=body)

    def get_order(self, order_id: OrderId) -> Order:
        if order_id.value in self._cache:
            try:
                native = self._transport.get(f"/orders/{order_id.value}")
                order = self._wire.to_order(native)
                self._cache[order_id.value] = order
                return order
            except Exception:
                return self._cache[order_id.value]
        native = self._transport.get(f"/orders/{order_id.value}")
        order = self._wire.to_order(native)
        self._cache[order_id.value] = order
        return order

    def get_orderbook(self) -> list[Order]:
        data = self._transport.get("/orders")
        rows = data if isinstance(data, list) else data.get("data", [])
        return [self._wire.to_order(r) for r in rows]
