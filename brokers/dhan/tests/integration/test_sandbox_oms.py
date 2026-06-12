"""Sandbox OMS integration tests for Dhan."""

from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal
from typing import Any

import pytest

from brokers.common.core.connection import Capability
from brokers.common.core.enums import (
    ExchangeSegment,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.models import OrderRequest

pytestmark = [
    pytest.mark.dhan,
    pytest.mark.integration,
    pytest.mark.sandbox,
]

TERMINAL_STATUSES = {
    OrderStatus.EXECUTED,
    OrderStatus.REJECTED,
    OrderStatus.CANCELLED,
}


def test_sandbox_connects_and_exposes_oms_capabilities(sandbox_broker: Any) -> None:
    assert sandbox_broker.is_connected()
    assert sandbox_broker.settings.environment.upper() == "SANDBOX"
    assert sandbox_broker.has_capability(Capability.ORDER_COMMAND)
    assert sandbox_broker.has_capability(Capability.ORDER_QUERY)
    assert sandbox_broker.has_capability(Capability.PORTFOLIO)


def test_sandbox_place_query_and_cancel_order(sandbox_broker: Any) -> None:
    correlation_id = f"xv2-sandbox-{uuid.uuid4()}"
    order = _build_order(sandbox_broker, correlation_id)

    response = sandbox_broker.place_order(order)
    assert response.success, response.message
    assert response.order_id

    order_id = response.order_id
    queried = _wait_for_order(sandbox_broker, correlation_id, order_id)
    assert queried is not None

    if _can_modify(queried):
        modified = sandbox_broker.order_client.modify_order(order_id, price=order.price)
        assert isinstance(modified, dict)

    cancel_response = sandbox_broker.order_client.cancel_order(order_id)
    assert isinstance(cancel_response, dict)


def _build_order(broker: Any, correlation_id: str) -> OrderRequest:
    security_id = os.getenv("DHAN_TEST_SECURITY_ID", "2885")
    exchange_segment = ExchangeSegment(
        os.getenv("DHAN_TEST_EXCHANGE_SEGMENT", ExchangeSegment.NSE.value)
    )
    product_type = ProductType(os.getenv("DHAN_TEST_PRODUCT_TYPE", ProductType.INTRADAY.value))
    quantity = int(os.getenv("DHAN_TEST_QUANTITY", "1"))
    price = _limit_price(broker, security_id, exchange_segment)

    return OrderRequest(
        security_id=security_id,
        exchange_segment=exchange_segment,
        transaction_type=TransactionType.BUY,
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
        product_type=product_type,
        validity=Validity.DAY,
        correlation_id=correlation_id,
    )


def _limit_price(broker: Any, security_id: str, exchange_segment: ExchangeSegment) -> Decimal:
    explicit_price = os.getenv("DHAN_TEST_LIMIT_PRICE")
    if explicit_price:
        return Decimal(explicit_price)

    quote = broker.get_quote(security_id, exchange_segment)
    if quote is None or quote.last_price <= 0:
        pytest.skip("quote unavailable; set DHAN_TEST_LIMIT_PRICE to run sandbox order test")

    return quote.last_price


def _wait_for_order(
    broker: Any, correlation_id: str, order_id: str, timeout_seconds: int = 30
) -> Any | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        queried = _find_order(broker, correlation_id, order_id)
        if queried is not None:
            return queried
        time.sleep(1)
    return None


def _find_order(broker: Any, correlation_id: str, order_id: str) -> Any | None:
    query = broker.get_capability(Capability.ORDER_QUERY)
    if query is not None:
        for order in query.get_order_list() or []:
            if _matches(order, correlation_id, order_id):
                return order

    for order in broker.get_order_list() or []:
        if _matches(order, correlation_id, order_id):
            return order

    by_id = broker.get_order_by_id(order_id)
    if by_id:
        return by_id

    return None


def _matches(order: Any, correlation_id: str, order_id: str) -> bool:
    order_id_value = getattr(order, "order_id", None) or (
        order.get("orderId") if isinstance(order, dict) else None
    )
    correlation_value = getattr(order, "correlation_id", None) or (
        order.get("correlationId") if isinstance(order, dict) else None
    )
    return order_id_value == order_id or correlation_value == correlation_id


def _can_modify(order: Any) -> bool:
    status = getattr(order, "status", None) or (
        order.get("orderStatus") or order.get("status") if isinstance(order, dict) else None
    )
    return status not in TERMINAL_STATUSES
