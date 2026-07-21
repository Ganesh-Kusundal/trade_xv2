"""Build OMS submit_fn callables that delegate to broker gateways."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from application.oms.order_manager import OmsOrderCommand
from domain.entities import Order
from domain.enums import OrderStatus
from domain.entities import OrderResponse
from domain.orders.requests import OrderRequest
from domain.ports.broker_gateway import OrderTransportPort
from domain.ports.order_placement import OrderPlacementPort
from domain.ports.execution_context import oms_managed
from domain.ports.time_service import ClockPort, get_current_clock


def order_from_response(
    command: OmsOrderCommand,
    response: OrderResponse,
    clock: ClockPort | None = None,
) -> Order:
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
        timestamp=(clock or get_current_clock()).now(),
        correlation_id=command.correlation_id,
    )


def make_gateway_submit_fn(
    gateway: OrderTransportPort | OrderPlacementPort,
    clock: ClockPort | None = None,
) -> Callable[[OmsOrderCommand], Order]:
    """Return an OMS ``submit_fn`` that sends orders through *gateway*.

    The OMS owns pre-submit validation; broker adapters remain free to enforce
    their own boundary checks without needing a transport policy flag.
    """
    _clock = clock or get_current_clock()

    def submit(command: OmsOrderCommand) -> Order:
        with oms_managed():
            request = OrderRequest(
                symbol=command.symbol,
                exchange=command.exchange,
                transaction_type=command.side,
                quantity=command.quantity,
                price=command.price,
                order_type=command.order_type,
                product_type=command.product_type,
                correlation_id=command.correlation_id,
            )
            response = gateway.place_order(request)
        return order_from_response(command, response, clock=_clock)

    return submit
