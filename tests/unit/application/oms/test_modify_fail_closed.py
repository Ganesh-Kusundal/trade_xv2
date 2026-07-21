"""OMS modify must fail closed when broker response lacks success=True."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from unittest.mock import MagicMock

from application.oms._internal.order_lifecycle import OrderLifecycle
from domain import Order, OrderStatus, OrderType, ProductType, Side, Validity
from domain.orders.requests import ModifyOrderRequest


@dataclass
class _BareResponse:
    message: str = "broker rejected"


def _lifecycle() -> OrderLifecycle:
    return OrderLifecycle(
        state_validator=MagicMock(),
        audit_logger=MagicMock(),
        trade_recorder=MagicMock(),
        idempotency_guard=MagicMock(),
        risk_manager=None,
        publish=MagicMock(),
    )


def test_modify_fails_when_response_has_no_success_attr() -> None:
    """getattr(response, 'success', False) — missing success must not pass."""
    order = Order(
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=100,
        status=OrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
    )
    orders = {"O1": order}
    lock = threading.RLock()

    result = _lifecycle().modify_order(
        lock,
        orders,
        {},
        ModifyOrderRequest(order_id="O1", price=101),
        modify_fn=lambda _r: _BareResponse(message="no success field"),
    )
    assert result.success is False
