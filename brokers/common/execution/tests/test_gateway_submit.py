"""Integration tests for gateway submit_fn wiring."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain import OrderStatus, Side
from domain.entities import OrderResponse
from brokers.common.execution.gateway_submit import make_gateway_submit_fn, order_from_response
from brokers.common.oms.order_manager import OmsOrderCommand


def test_order_from_response_success() -> None:
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:gateway:1",
    )
    order = order_from_response(
        cmd,
        OrderResponse.ok(order_id="BR-123", status=OrderStatus.OPEN),
    )
    assert order.order_id == "BR-123"
    assert order.symbol == "RELIANCE"


def test_make_gateway_submit_fn_transport_only() -> None:
    gateway = MagicMock()
    gateway.place_order.return_value = OrderResponse.ok(order_id="BR-456")

    cmd = OmsOrderCommand(
        symbol="GOLD",
        exchange="MCX",
        side=Side.BUY,
        quantity=1,
        correlation_id="test:gateway:2",
    )
    submit = make_gateway_submit_fn(gateway, transport_only=True)
    order = submit(cmd)

    assert order.order_id == "BR-456"
    gateway.place_order.assert_called_once()
    _, kwargs = gateway.place_order.call_args
    assert kwargs["transport_only"] is True
    assert kwargs["exchange"] == "MCX"


def test_make_gateway_submit_fn_raises_on_broker_failure() -> None:
    gateway = MagicMock()
    gateway.place_order.return_value = OrderResponse.fail("broker down")

    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        correlation_id="test:gateway:3",
    )
    with pytest.raises(RuntimeError, match="broker down"):
        make_gateway_submit_fn(gateway)(cmd)
