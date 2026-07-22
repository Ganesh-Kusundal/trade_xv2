"""Dhan gateway + FakeTransport — real gateway, injectable transport (no gateway mocks)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Quantity
from plugins.brokers.dhan import DhanGateway
from tests.integration.adapter_harness import AdapterTestHarness


class FakeTransport:
    """Fixture-backed get/post — stands in for Dhan HTTP in CI."""

    def __init__(self, responses: dict[tuple[str, str], dict] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def get(self, path: str, **kwargs: Any) -> dict:
        self.calls.append(("GET", path, kwargs))
        return dict(self.responses.get(("GET", path), {}))

    def post(self, path: str, **kwargs: Any) -> dict:
        self.calls.append(("POST", path, kwargs))
        return dict(self.responses.get(("POST", path), {}))

    def put(self, path: str, **kwargs: Any) -> dict:
        self.calls.append(("PUT", path, kwargs))
        return dict(self.responses.get(("PUT", path), {}))

    def delete(self, path: str, **kwargs: Any) -> dict:
        self.calls.append(("DELETE", path, kwargs))
        return dict(self.responses.get(("DELETE", path), {}))


def _quote_fixture() -> dict:
    # ponytail: native-like Dhan quote shape, not a live payload dump
    return {
        "data": {
            "2885": {
                "bid": 2499.5,
                "ask": 2500.5,
                "bid_qty": 100,
                "ask_qty": 80,
                "ltp": 2500.0,
                "last_trade_time": "2024-01-15T10:00:00+05:30",
            }
        }
    }


def _place_ack_fixture() -> dict:
    return {
        "orderId": "DHAN-ORD-42",
        "orderStatus": "TRANSIT",
        "transactionType": "BUY",
        "securityId": "2885",
        "quantity": 10,
        "price": 0.0,
        "orderType": "MARKET",
    }


def test_dhan_adapter_harness_quote_and_place_order() -> None:
    transport = FakeTransport(
        {
            ("GET", "/marketfeed/quote"): _quote_fixture(),
            ("POST", "/orders"): _place_ack_fixture(),
            ("GET", "/positions"): {"data": []},
            ("GET", "/fundlimit"): {"data": {"availabelBalance": 500000}},
        }
    )
    from plugins.brokers.dhan.config import DhanConfig

    gateway = DhanGateway(
        config=DhanConfig(access_token="dhan-static"),
        transport=transport,
    )
    harness = AdapterTestHarness(adapter=gateway)
    harness.test_connect()
    gateway.connect()
    assert gateway.authenticate() is True

    instrument_id = InstrumentId(value="NSE:RELIANCE")
    quote = harness.test_get_quote(instrument_id)
    assert quote.bid.value == Decimal("2499.5")
    assert quote.ask.value == Decimal("2500.5")

    cmd = PlaceOrderCommand(
        instrument_id=instrument_id,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("10")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    order_id = harness.test_place_fill(cmd)
    assert order_id.value == "DHAN-ORD-42"
    assert gateway.get_funds().balance.amount == Decimal("500000")
    order = gateway.get_order(order_id)
    assert order.status.name == "SUBMITTED"

    received: list = []
    gateway.stream(instrument_id, on_quote=received.append)
    gateway.connection.streaming.feed_raw(
        {
            "instrument_id": "NSE:RELIANCE",
            "data": {
                "2885": {
                    "bid": 1,
                    "ask": 2,
                    "bid_qty": 1,
                    "ask_qty": 1,
                    "last_trade_time": "2024-01-15T10:00:00+05:30",
                }
            },
        }
    )
    assert len(received) == 1

    assert any(c[0] == "GET" and "quote" in c[1] for c in transport.calls)
    assert any(c[0] == "POST" and "order" in c[1].lower() for c in transport.calls)
    gateway.close()
