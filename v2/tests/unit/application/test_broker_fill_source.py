"""BrokerFillSource must not invent FILLED when venue only acks order id."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from application.execution.fill_sources import BrokerFillSource
from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Quantity


class _AckOnlyAdapter:
    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return OrderId(value="LIVE-1")

    def cancel_order(self, order_id: OrderId) -> None:
        return None


class _GetOrderAdapter(_AckOnlyAdapter):
    def get_order(self, order_id: OrderId):
        from domain.entities import Order

        o = Order(
            order_id=order_id,
            instrument_id=InstrumentId(value="NSE:X"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(value=Decimal("1")),
            price=None,
            time_in_force=TimeInForce.DAY,
            status=OrderStatus.PENDING,
            correlation_id=CorrelationId(value=uuid4()),
        )
        o.transition_to(OrderStatus.SUBMITTED)
        return o


def _cmd() -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId(value="NSE:X"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )


def test_broker_fill_source_returns_submitted_not_filled() -> None:
    src = BrokerFillSource(adapter=_AckOnlyAdapter())
    order = src.submit(_cmd())
    assert order.status is OrderStatus.SUBMITTED
    assert order.order_id.value == "LIVE-1"


def test_broker_fill_source_uses_get_order_when_present() -> None:
    src = BrokerFillSource(adapter=_GetOrderAdapter())
    order = src.submit(_cmd())
    assert order.status is OrderStatus.SUBMITTED
