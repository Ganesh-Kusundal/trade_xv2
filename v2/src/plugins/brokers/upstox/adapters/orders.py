"""Upstox orders adapter."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderStatus
from domain.value_objects import OrderId
from plugins.brokers.common.idempotency import IdempotencyCache
from plugins.brokers.upstox.wire import UpstoxWire
from shared.errors import MappingError

if TYPE_CHECKING:
    from plugins.brokers.common.transport import BaseTransport

logger = logging.getLogger(__name__)


class UpstoxOrdersAdapter:
    def __init__(self, transport: BaseTransport, wire: UpstoxWire) -> None:
        self._transport = transport
        self._wire = wire
        self._cache: dict[str, Order] = {}
        self._idempotency = IdempotencyCache()

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        cid = str(command.correlation_id.value)
        cached = self._idempotency.get(cid)
        if cached is not None:
            return OrderId(value=cached)
        if not self._idempotency.reserve(cid):
            for _ in range(50):
                cached = self._idempotency.get(cid)
                if cached is not None:
                    return OrderId(value=cached)
                time.sleep(0.1)
        post_sent = False
        try:
            body = self._wire.from_place_command(command)
            ack = self._transport.post("/order/place", json=body)
            post_sent = True
            oid = self._wire.to_order_id(ack)
        except Exception:
            if not post_sent:
                self._idempotency.clear_reservation(cid)
            raise
        if post_sent:
            self._idempotency.commit(cid, oid.value)
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
        order = order.transition_to(OrderStatus.SUBMITTED)
        self._cache[oid.value] = order
        return oid

    def cancel_order(self, order_id: OrderId) -> None:
        self._transport.delete(f"/order/cancel", params={"order_id": order_id.value})
        cached = self._cache.get(order_id.value)
        if cached is not None and cached.status not in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        ):
            self._cache[order_id.value] = cached.transition_to(OrderStatus.CANCELLED)

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        body = self._wire.from_place_command(command)
        body["order_id"] = order_id.value
        self._transport.put("/order/modify", json=body)

    def get_order(self, order_id: OrderId) -> Order:
        if order_id.value in self._cache:
            try:
                native = self._transport.get(f"/order/history", params={"order_id": order_id.value})
                rows = native.get("data", native) if isinstance(native, dict) else native
                if isinstance(rows, list) and rows:
                    order = self._wire.to_order(rows[-1])
                    self._cache[order_id.value] = order
                    return order
            except Exception:
                return self._cache[order_id.value]
            return self._cache[order_id.value]
        native = self._transport.get("/order/history", params={"order_id": order_id.value})
        rows = native.get("data", []) if isinstance(native, dict) else native
        order = self._wire.to_order(rows[-1] if rows else {"order_id": order_id.value, "status": "open"})
        self._cache[order_id.value] = order
        return order

    def get_orderbook(self) -> list[Order]:
        data = self._transport.get("/order/retrieve-all")
        rows = data if isinstance(data, list) else data.get("data", [])
        orders: list[Order] = []
        for r in rows:
            try:
                orders.append(self._wire.to_order(r))
            except MappingError as exc:
                logger.warning("upstox_orderbook_row_unmapped: %s", exc)
        return orders
