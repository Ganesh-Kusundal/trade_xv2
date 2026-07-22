"""Paper orders — immediate fill at mid (market) or limit price."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.entities import Order, Position
from domain.enums import OrderSide, OrderStatus, OrderType
from domain.value_objects import Money, OrderId, Price, Quantity

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperOrdersAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        self._conn.require_connected()
        quote = self._conn.quotes.get(command.instrument_id)
        if quote is None:
            raise KeyError(f"no quote seeded for {command.instrument_id.value}")

        fill_price = self._fill_price(command, quote)
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
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.FILLED)
        order.filled_quantity = command.quantity
        self._conn.orders[order_id.value] = self._conn.wire.to_order(order)
        self._apply_fill(command.side, command.instrument_id, command.quantity, fill_price)
        return order_id

    def cancel_order(self, order_id: OrderId) -> None:
        self._conn.require_connected()
        order = self._conn.orders.get(order_id.value)
        if order is None:
            raise KeyError(f"unknown order {order_id.value}")
        order.transition_to(OrderStatus.CANCELLED)

    def get_order(self, order_id: OrderId) -> Order:
        order = self._conn.orders.get(order_id.value)
        if order is None:
            raise KeyError(f"unknown order {order_id.value}")
        return order

    def get_orderbook(self) -> list[Order]:
        return list(self._conn.orders.values())

    @staticmethod
    def _fill_price(command: PlaceOrderCommand, quote) -> Price:
        if command.order_type == OrderType.LIMIT and command.price is not None:
            return command.price
        mid = (quote.bid.value + quote.ask.value) / Decimal("2")
        return Price(value=mid)

    def _apply_fill(
        self,
        side: OrderSide,
        instrument_id,
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

        # same-direction add → VWAP; reduce/flip keeps prior avg unless flipped
        if (pos.quantity.value > 0) == (delta > 0):
            avg = (
                abs(pos.quantity.value) * pos.avg_price.value + abs(delta) * price.value
            ) / abs(new_qty)
            pos.avg_price = Price(value=avg)
        elif (pos.quantity.value > 0) != (new_qty > 0):
            pos.avg_price = price
        pos.quantity = Quantity(value=new_qty)
