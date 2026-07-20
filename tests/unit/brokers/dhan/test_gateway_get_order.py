"""C0.7a — DhanBrokerGateway exposes get_order and delegates end-to-end.

Contract test for R9 (P0): the gateway must expose ``get_order(order_id)``
and delegate to the existing execution helper (``OrdersAdapter.get_order``
in ``brokers/dhan/execution/orders.py``), which in turn calls the underlying
Dhan client at ``GET /orders/{order_id}``.

The gateway method itself is a thin facade (see ``gateway.py::get_order``);
this test proves the whole chain works without duplicating any logic:

    DhanBrokerGateway.get_order
        -> DhanConnection.orders (OrdersAdapter).get_order   # execution helper
            -> DhanHttpClient.get("/orders/{order_id}")       # underlying client
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.dhan.execution.orders import OrdersAdapter
from brokers.dhan.wire import DhanBrokerGateway
from domain import Order, OrderStatus


def _make_gateway_with_real_adapter(fake_client, resolver) -> DhanBrokerGateway:
    """Build a gateway whose ``_conn.orders`` is a *real* OrdersAdapter.

    The OrdersAdapter is wired to the (mocked) underlying Dhan client so we
    can assert the delegation reaches all the way down to the HTTP call.
    """
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)

    conn = MagicMock()
    conn.orders = adapter

    gw = object.__new__(DhanBrokerGateway)
    gw._conn = conn
    return gw


def _order_payload(order_id: str = "ORD-123") -> dict:
    return {
        "orderId": order_id,
        "tradingSymbol": "RELIANCE",
        "exchangeSegment": "NSE_EQ",
        "transactionType": "BUY",
        "quantity": 10,
        "filledQty": 10,
        "price": 2450.0,
        "averagePrice": 2449.5,
        "orderStatus": "COMPLETE",
    }


@pytest.mark.unit
def test_gateway_get_order_delegates_to_orders_adapter(fake_client, resolver) -> None:
    """Gateway.get_order must forward to OrdersAdapter.get_order (the
    execution helper) and return whatever it returns."""
    gw = _make_gateway_with_real_adapter(fake_client, resolver)
    fake_client.set_response("GET", "/orders/ORD-123", {"data": _order_payload()})

    result = gw.get_order("ORD-123")

    # Delegation reached the execution helper, which hit the underlying client.
    assert fake_client.calls_for("GET", "/orders/ORD-123") is not None
    # Return shape matches get_orderbook's style: a domain Order.
    assert isinstance(result, Order)
    assert result.order_id == "ORD-123"
    assert result.symbol == "RELIANCE"
    assert result.status == OrderStatus.FILLED


@pytest.mark.unit
def test_gateway_get_order_uses_direct_endpoint_not_orderbook(fake_client, resolver) -> None:
    """Critical: get_order must call GET /orders/{id}, NOT scan the full
    orderbook. This is the whole point of the dedicated endpoint."""
    gw = _make_gateway_with_real_adapter(fake_client, resolver)
    fake_client.set_response("GET", "/orders/ORD-456", {"data": _order_payload("ORD-456")})

    gw.get_order("ORD-456")

    assert fake_client.calls_for("GET", "/orders/ORD-456") is not None
    assert fake_client.calls_for("GET", "/orders") == []


@pytest.mark.unit
def test_gateway_get_order_returns_none_on_client_error(fake_client, resolver) -> None:
    """When the underlying client raises (order not found / broker error),
    the gateway surfaces None rather than propagating the exception."""
    gw = _make_gateway_with_real_adapter(fake_client, resolver)
    fake_client.set_side_effect("GET", "/orders/NOPE", Exception("Order not found"))

    result = gw.get_order("NOPE")

    assert result is None
    assert fake_client.calls_for("GET", "/orders/NOPE") is not None
