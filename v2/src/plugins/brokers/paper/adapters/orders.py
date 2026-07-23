"""Paper orders — immediate fill (configurable) at mid or limit price."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.entities import Order, Position
from domain.enums import OrderSide, OrderStatus, OrderType
from domain.value_objects import Money, OrderId, Price, Quantity
from plugins.brokers.common.constants import DEFAULT_FILL_PRICE

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperOrdersAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        self._conn.require_connected()

        order_id = OrderId(value=f"paper-{uuid4().hex[:12]}")
        order = Order(
            order_id=order_id,
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

        if self._conn.auto_fill:
            order = order.transition_to(OrderStatus.FILLED)
            fill_price = self._fill_price(command)
            order = replace(order, filled_quantity=command.quantity)
            self._apply_fill(command.side, command.instrument_id, command.quantity, fill_price)

        self._conn.orders[order_id.value] = order
        return order_id

    def cancel_order(self, order_id: OrderId) -> None:
        self._conn.require_connected()
        order = self._conn.orders.get(order_id.value)
        if order is None:
            raise KeyError(f"unknown order {order_id.value}")
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            raise ValueError(f"cannot cancel order in {order.status.value} status")
        self._conn.orders[order_id.value] = order.transition_to(OrderStatus.CANCELLED)

    def modify_order(self, order_id: OrderId, command: PlaceOrderCommand) -> None:
        self._conn.require_connected()
        order = self._conn.orders.get(order_id.value)
        if order is None:
            raise KeyError(f"unknown order {order_id.value}")
        self._conn.orders[order_id.value] = replace(
            order, price=command.price, quantity=command.quantity
        )

    def get_order(self, order_id: OrderId) -> Order:
        order = self._conn.orders.get(order_id.value)
        if order is None:
            raise KeyError(f"unknown order {order_id.value}")
        return order

    def get_orderbook(self) -> list[Order]:
        return list(self._conn.orders.values())

    def _fill_price(self, command: PlaceOrderCommand) -> Price:
        if command.order_type == OrderType.LIMIT and command.price is not None:
            return command.price
        quote = self._conn.quotes.get(command.instrument_id)
        if quote is not None:
            mid = (quote.bid.value + quote.ask.value) / Decimal("2")
            return Price(value=mid)
        return Price(value=DEFAULT_FILL_PRICE)

    def _apply_fill(
        self,
        side: OrderSide,
        instrument_id: InstrumentId,
        qty: Quantity,
        price: Price,
    ) -> None:
        notional = price.value * qty.value
        cash = self._conn.cash
        if side is OrderSide.BUY:
            self._conn.cash = Money(amount=cash.amount - notional, currency=cash.currency)
            delta = qty.value
        else:
            self._conn.cash = Money(amount=cash.amount + notional, currency=cash.currency)
            delta = -qty.value

        zero = Money(amount=Decimal("0"), currency=cash.currency)
        pos = self._conn.positions.get(instrument_id)
        if pos is None:
            self._conn.positions[instrument_id] = Position(
                instrument_id=instrument_id,
                quantity=Quantity(value=delta),
                avg_price=price,
                realized_pnl=zero,
                unrealized_pnl=zero,
            )
            return

        new_qty = pos.quantity.value + delta
        if new_qty == 0:
            del self._conn.positions[instrument_id]
            return

        if (pos.quantity.value > 0) == (delta > 0):
            avg = (
                abs(pos.quantity.value) * pos.avg_price.value + abs(delta) * price.value
            ) / abs(new_qty)
            new_pos = replace(pos, avg_price=Price(value=avg), quantity=Quantity(value=new_qty))
        elif (pos.quantity.value > 0) != (new_qty > 0):
            new_pos = replace(pos, avg_price=price, quantity=Quantity(value=new_qty))
        else:
            new_pos = replace(pos, quantity=Quantity(value=new_qty))
        self._conn.positions[instrument_id] = new_pos

