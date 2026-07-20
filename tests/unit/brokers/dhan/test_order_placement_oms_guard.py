"""Regression: Dhan OrderPlacer must not publish ORDER_PLACED under OMS."""

from __future__ import annotations

from brokers.dhan.execution.orders import OrdersAdapter
from domain.models.dtos import BrokerOrderPayload
from domain.ports.execution_context import oms_managed
from infrastructure.event_bus import EventBus


def test_place_order_skips_order_placed_when_oms_managed(fake_client, resolver):
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-OMS"}})
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))
    adapter = OrdersAdapter(
        fake_client,
        resolver,
        event_bus=bus,
        allow_live_orders=True,
    )

    request = BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        correlation_id="oms-cid",
    )
    with oms_managed():
        response = adapter.place_order(request)

    assert response.success
    assert len(received) == 0
    assert len(fake_client.calls_for("POST", "/orders")) == 1


def test_place_order_publishes_order_placed_without_oms_managed(fake_client, resolver):
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-DIRECT"}})
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))
    adapter = OrdersAdapter(
        fake_client,
        resolver,
        event_bus=bus,
        allow_live_orders=True,
    )

    response = adapter.place_order(
        BrokerOrderPayload(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            correlation_id="direct-cid",
        )
    )

    assert response.success
    assert len(received) == 1
