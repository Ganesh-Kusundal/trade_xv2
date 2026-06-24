"""Tests for FakeBrokerGateway test double."""

from __future__ import annotations

from decimal import Decimal

from domain.entities import OrderResponse
from tests.fixtures.fake_broker_gateway import FakeBrokerGateway


class TestFakeBrokerGateway:
    def test_place_order_returns_success(self):
        gw = FakeBrokerGateway()
        result = gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            price=Decimal("2500"),
        )
        assert result.success
        assert result.order_id is not None

    def test_place_order_records_order(self):
        gw = FakeBrokerGateway()
        gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            price=Decimal("2500"),
        )
        orders = gw.get_orders()
        assert len(orders) == 1
        assert orders[0]["symbol"] == "RELIANCE"
        assert orders[0]["exchange"] == "NSE"
        assert orders[0]["side"] == "BUY"
        assert orders[0]["quantity"] == 10
        assert orders[0]["price"] == Decimal("2500")

    def test_place_order_increments_counter(self):
        gw = FakeBrokerGateway()
        assert gw.get_order_count() == 0
        gw.place_order(symbol="RELIANCE", exchange="NSE", side="BUY", quantity=1)
        assert gw.get_order_count() == 1
        gw.place_order(symbol="TCS", exchange="NSE", side="SELL", quantity=5)
        assert gw.get_order_count() == 2

    def test_place_order_generates_unique_ids(self):
        gw = FakeBrokerGateway()
        r1 = gw.place_order(symbol="RELIANCE", exchange="NSE", side="BUY", quantity=1)
        r2 = gw.place_order(symbol="TCS", exchange="NSE", side="SELL", quantity=5)
        assert r1.order_id != r2.order_id

    def test_set_default_response(self):
        gw = FakeBrokerGateway()
        gw.set_default_response(OrderResponse.ok(order_id="CUSTOM-001"))
        result = gw.place_order(symbol="RELIANCE", exchange="NSE", side="BUY", quantity=1)
        assert result.order_id == "CUSTOM-001"

    def test_set_response_for_symbol(self):
        gw = FakeBrokerGateway()
        gw.set_response_for_symbol("RELIANCE", OrderResponse.ok(order_id="REL-001"))
        gw.set_response_for_symbol("TCS", OrderResponse.ok(order_id="TCS-001"))

        r1 = gw.place_order(symbol="RELIANCE", exchange="NSE", side="BUY", quantity=1)
        r2 = gw.place_order(symbol="TCS", exchange="NSE", side="SELL", quantity=5)

        assert r1.order_id == "REL-001"
        assert r2.order_id == "TCS-001"

    def test_clear(self):
        gw = FakeBrokerGateway()
        gw.place_order(symbol="RELIANCE", exchange="NSE", side="BUY", quantity=1)
        gw.place_order(symbol="TCS", exchange="NSE", side="SELL", quantity=5)
        assert gw.get_order_count() == 2

        gw.clear()
        assert gw.get_order_count() == 0
        assert len(gw.get_orders()) == 0

    def test_records_correlation_id(self):
        gw = FakeBrokerGateway()
        gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            correlation_id="test:corr:123",
        )
        orders = gw.get_orders()
        assert orders[0]["correlation_id"] == "test:corr:123"

    def test_records_transport_only_flag(self):
        gw = FakeBrokerGateway()
        gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            transport_only=True,
        )
        orders = gw.get_orders()
        assert orders[0]["transport_only"] is True
