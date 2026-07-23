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
    # G4: Dhan returns depth in nested depth.buy/depth.sell arrays from /marketfeed/quote
    return {
        "data": {
            "NSE_EQ": {
                "2885": {
                    "last_price": 2500.0,
                    "ohlc": {"open": 2490.0, "high": 2510.0, "low": 2485.0, "close": 2495.0},
                    "volume": 100000,
                    "depth": {
                        "buy": [
                            {"price": 2499.5, "quantity": 100, "orders": 5},
                            {"price": 2499.0, "quantity": 200, "orders": 8},
                        ],
                        "sell": [
                            {"price": 2500.5, "quantity": 80, "orders": 3},
                            {"price": 2501.0, "quantity": 150, "orders": 6},
                        ],
                    },
                    "last_trade_time": "2024-01-15T10:00:00+05:30",
                }
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
            ("POST", "/marketfeed/quote"): _quote_fixture(),
            ("POST", "/orders"): _place_ack_fixture(),
            ("GET", "/orders"): {"data": []},
            ("GET", "/positions"): {"data": []},
            ("GET", "/fundlimit"): {"data": {"availabelBalance": 500000}},
        }
    )
    from plugins.brokers.dhan.config import DhanConfig

    gateway = DhanGateway(
        config=DhanConfig(access_token="dhan-static", allow_live_orders=True),
        transport=transport,
    )
    harness = AdapterTestHarness(adapter=gateway)
    harness.test_connect()
    gateway.connect()
    assert gateway.authenticate() is True

    # Register RELIANCE security ID for testing
    gateway.connection.wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")

    instrument_id = InstrumentId.parse("NSE:RELIANCE")
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

    harness.test_get_positions()
    harness.test_get_funds()
    harness.test_mass_status()
    harness.test_capabilities()

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

    assert any(c[0] == "POST" and "quote" in c[1] for c in transport.calls)
    assert any(c[0] == "POST" and "order" in c[1].lower() for c in transport.calls)
    gateway.close()
