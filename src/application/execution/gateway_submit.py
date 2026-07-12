"""Build OMS submit_fn callables that delegate to broker gateways."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from application.oms.order_manager import OmsOrderCommand
from domain import Order, OrderStatus
from domain.entities import OrderResponse
from domain.ports.broker_gateway import OrderTransportPort
from domain.ports.execution_context import oms_managed
from application.observability import trace_operation


def order_from_response(command: OmsOrderCommand, response: OrderResponse) -> Order:
    """Convert a broker :class:`OrderResponse` into a canonical :class:`Order`."""
    if not response.success:
        raise RuntimeError(response.message or "Order rejected by broker")
    order_id = response.order_id or response.broker_order_id or f"broker-{uuid.uuid4().hex[:12]}"
    return Order(
        order_id=order_id,
        symbol=command.symbol,
        exchange=command.exchange,
        side=command.side,
        order_type=command.order_type,
        quantity=command.quantity,
        filled_quantity=0,
        price=command.price,
        product_type=command.product_type,
        status=response.status if response.status else OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
        correlation_id=command.correlation_id,
    )


def make_gateway_submit_fn(
    gateway: OrderTransportPort,
) -> Callable[[OmsOrderCommand], Order]:
    """Return an OMS ``submit_fn`` that sends orders through *gateway*.

    The OMS owns pre-submit validation; broker adapters remain free to enforce
    their own boundary checks without needing a transport policy flag.
    """

    @trace_operation("gateway_submit")
    def submit(command: OmsOrderCommand) -> Order:
        with oms_managed():
            response = gateway.place_order(
                symbol=command.symbol,
                exchange=command.exchange,
                side=command.side.value,
                quantity=command.quantity,
                price=command.price if command.price else Decimal("0"),
                order_type=command.order_type.value,
                product_type=command.product_type.value,
                correlation_id=command.correlation_id,
            )
        return order_from_response(command, response)

    return submit
