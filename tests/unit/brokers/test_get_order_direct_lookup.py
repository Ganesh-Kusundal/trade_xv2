"""Cross-broker get_order direct lookup contract (Task 2.1)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from brokers.providers.dhan.wire import DhanWireAdapter
from brokers.providers.upstox.wire import UpstoxWireAdapter
from domain import OrderResponse, OrderStatus
from tests.fixtures.domain_helpers import make_order


def _make_order(order_id: str = "ORD-123", status: OrderStatus = OrderStatus.OPEN):
    return make_order(order_id=order_id, status=status, order_type="MARKET", quantity=1)


@pytest.fixture(params=["dhan", "upstox"])
def gateway_bundle(request):
    if request.param == "dhan":
        conn = MagicMock()
        gw = DhanWireAdapter(conn)
        return request.param, gw, conn.orders, conn.orders
    broker = MagicMock()
    broker.settings = MagicMock(analytics_only=False, allow_live_orders=True)
    gw = UpstoxWireAdapter(broker)
    return request.param, gw, broker.order_query, broker.order_command


@pytest.mark.unit
def test_get_order_calls_direct_adapter(gateway_bundle) -> None:
    broker_id, gw, order_lookup, _ = gateway_bundle
    expected = _make_order("ORD-123")
    order_lookup.get_order.return_value = expected

    result = gw.get_order("ORD-123")

    order_lookup.get_order.assert_called_once_with("ORD-123")
    assert result is expected
    if broker_id == "dhan":
        gw._conn.orders.get_orderbook.assert_not_called()


@pytest.mark.unit
def test_get_order_returns_none_when_lookup_fails(gateway_bundle) -> None:
    broker_id, gw, order_lookup, _ = gateway_bundle
    if broker_id == "dhan":
        from domain.errors import OrderError

        order_lookup.get_order.side_effect = RuntimeError("broker timeout")
        with pytest.raises(OrderError):
            gw.get_order("NONEXISTENT")
    else:
        order_lookup.get_order.return_value = None
        assert gw.get_order("NONEXISTENT") is None
    order_lookup.get_order.assert_called_once_with("NONEXISTENT")


@pytest.mark.unit
def test_get_order_raises_on_transport_failure(gateway_bundle) -> None:
    broker_id, gw, order_lookup, _ = gateway_bundle
    if broker_id != "dhan":
        pytest.skip("Dhan-only transport error contract")
    from domain.errors import OrderError

    order_lookup.get_order.side_effect = RuntimeError("broker timeout")

    with pytest.raises(OrderError):
        gw.get_order("ORD-999")


@pytest.mark.unit
def test_cancel_order_verification_uses_direct_lookup(gateway_bundle) -> None:
    broker_id, gw, order_lookup, order_command = gateway_bundle
    if broker_id == "dhan":
        from tests.unit.brokers.dhan.test_gateway_get_order import (
            _make_gateway_with_real_adapter,
        )
        from tests.support.brokers.dhan.fixtures import FakeHttpClient

        client = FakeHttpClient()
        client.set_response("DELETE", "/orders/ORD-123", {"status": "success"})
        client.set_response(
            "GET",
            "/orders/ORD-123",
            {
                "data": {
                    "orderId": "ORD-123",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 1,
                    "filledQty": 0,
                    "orderStatus": "CANCELLED",
                }
            },
        )
        from brokers.providers.dhan.resolver import SymbolResolver

        resolver = SymbolResolver()
        gw = _make_gateway_with_real_adapter(client, resolver)
        order_lookup = client
    else:
        order_command.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled"
        )
        order_lookup.get_order.return_value = _make_order("ORD-123", OrderStatus.CANCELLED)

    result = gw.cancel_order("ORD-123")

    assert result.success is True
    if broker_id == "dhan":
        assert client.calls_for("GET", "/orders/ORD-123") is not None
    else:
        order_lookup.get_order.assert_called_once_with("ORD-123")


@pytest.mark.unit
def test_cancel_order_detects_race_condition_fill(gateway_bundle) -> None:
    broker_id, gw, order_lookup, order_command = gateway_bundle
    if broker_id == "dhan":
        from tests.unit.brokers.dhan.test_gateway_get_order import (
            _make_gateway_with_real_adapter,
        )
        from tests.support.brokers.dhan.fixtures import FakeHttpClient

        client = FakeHttpClient()
        client.set_response("DELETE", "/orders/ORD-123", {"status": "success"})
        client.set_response(
            "GET",
            "/orders/ORD-123",
            {
                "data": {
                    "orderId": "ORD-123",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 1,
                    "filledQty": 1,
                    "orderStatus": "TRADED",
                }
            },
        )
        from brokers.providers.dhan.resolver import SymbolResolver

        resolver = SymbolResolver()
        gw = _make_gateway_with_real_adapter(client, resolver)
    else:
        order_command.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-123", message="Cancelled"
        )
        order_lookup.get_order.return_value = _make_order("ORD-123", OrderStatus.FILLED)

    result = gw.cancel_order("ORD-123")

    assert result.success is False


@pytest.mark.unit
def test_cancel_order_fails_when_post_verify_lookup_fails(gateway_bundle) -> None:
    broker_id, gw, order_lookup, _ = gateway_bundle
    if broker_id != "dhan":
        pytest.skip("Dhan-only post-verify transport failure contract")
    from tests.unit.brokers.dhan.test_gateway_get_order import (
        _make_gateway_with_real_adapter,
    )
    from tests.support.brokers.dhan.fixtures import FakeHttpClient

    client = FakeHttpClient()
    client.set_response("DELETE", "/orders/ORD-123", {"status": "success"})
    client.set_side_effect("GET", "/orders/ORD-123", RuntimeError("purged"))
    from brokers.providers.dhan.resolver import SymbolResolver

    gw = _make_gateway_with_real_adapter(client, SymbolResolver())

    result = gw.cancel_order("ORD-123")
    assert result.success is False
