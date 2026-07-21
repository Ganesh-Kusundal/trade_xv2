"""Post-cancel fill detection on Dhan OrderCanceller (H1 port from Upstox)."""

from __future__ import annotations

import pytest

from brokers.providers.dhan.execution.order_cancellation import OrderCanceller
from brokers.providers.dhan.execution.orders import OrdersAdapter
from domain import OrderStatus


def _filled_order_payload(order_id: str = "ORD-123") -> dict:
    return {
        "orderId": order_id,
        "tradingSymbol": "RELIANCE",
        "exchangeSegment": "NSE_EQ",
        "transactionType": "BUY",
        "quantity": 10,
        "filledQty": 10,
        "price": 2450.0,
        "averagePrice": 2449.5,
        "orderStatus": "TRADED",
    }


@pytest.mark.unit
def test_cancel_order_verifies_not_filled(fake_client, resolver) -> None:
    fake_client.set_response("DELETE", "/orders/ORD-123", {"status": "success"})
    fake_client.set_response(
        "GET",
        "/orders/ORD-123",
        {"data": {**_filled_order_payload(), "orderStatus": "CANCELLED", "filledQty": 0}},
    )
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)

    result = adapter.cancel_order("ORD-123")

    assert result.success is True
    assert fake_client.calls_for("GET", "/orders/ORD-123") is not None


@pytest.mark.unit
def test_cancel_order_detects_race_fill(fake_client, resolver) -> None:
    fake_client.set_response("DELETE", "/orders/ORD-456", {"status": "success"})
    fake_client.set_response("GET", "/orders/ORD-456", {"data": _filled_order_payload("ORD-456")})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)

    result = adapter.cancel_order("ORD-456")

    assert result.success is False
    assert "already filled" in (result.message or "").lower()
    assert result.status == OrderStatus.FILLED


@pytest.mark.unit
def test_cancel_order_fails_when_post_verify_lookup_fails(fake_client, resolver) -> None:
    fake_client.set_response("DELETE", "/orders/ORD-789", {"status": "success"})
    fake_client.set_side_effect("GET", "/orders/ORD-789", RuntimeError("broker timeout"))
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)

    result = adapter.cancel_order("ORD-789")

    assert result.success is False


@pytest.mark.unit
def test_canceller_without_lookup_skips_verify(fake_client) -> None:
    fake_client.set_response("DELETE", "/orders/ORD-1", {"status": "success"})
    canceller = OrderCanceller(fake_client, allow_live_orders=True)

    result = canceller.cancel_order("ORD-1")

    assert result.success is True
    assert not fake_client.calls_for("GET", "/orders/ORD-1")
