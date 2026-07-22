"""Upstox gateway + FakeTransport — real gateway, injectable transport (no gateway mocks)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Quantity
from plugins.brokers.upstox import UpstoxGateway
from tests.integration.adapter_harness import AdapterTestHarness


class FakeTransport:
    """Fixture-backed get/post — stands in for Upstox HTTP in CI."""

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
    # ponytail: native-like Upstox quote shape for sandbox wire mapping
    return {
        "status": "success",
        "data": {
            "NSE_EQ:RELIANCE": {
                "last_price": 2500.0,
                "depth": {
                    "buy": [{"price": 2499.5, "quantity": 100}],
                    "sell": [{"price": 2500.5, "quantity": 80}],
                },
                "timestamp": "2024-01-15T10:00:00+05:30",
            }
        },
    }


def _place_ack_fixture() -> dict:
    return {
        "status": "success",
        "data": {
            "order_id": "UPX-ORD-99",
            "status": "open",
            "transaction_type": "BUY",
            "quantity": 10,
            "order_type": "MARKET",
            "instrument_token": "NSE_EQ|RELIANCE",
        },
    }


def test_upstox_adapter_harness_quote_and_place_order() -> None:
    transport = FakeTransport(
        {
            ("GET", "/market-quote/quotes"): _quote_fixture(),
            ("POST", "/order/place"): _place_ack_fixture(),
            ("GET", "/portfolio/short-term-positions"): {"data": []},
            ("GET", "/user/get-funds-and-margin"): {
                "data": {"equity": {"available_margin": 100000}}
            },
        }
    )
    gateway = UpstoxGateway(transport=transport)
    harness = AdapterTestHarness(adapter=gateway)
    harness.test_connect()
    gateway.connect()
    assert gateway.authenticate() is False  # no token configured — fail closed

    from plugins.brokers.upstox.config import UpstoxConfig

    gateway = UpstoxGateway(
        config=UpstoxConfig(access_token="static-tok"),
        transport=transport,
    )
    gateway.connect()
    assert gateway.authenticate() is True

    instrument_id = InstrumentId(value="NSE:RELIANCE")
    quote = gateway.get_quote(instrument_id)
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
    order_id = gateway.place_order(cmd)
    assert order_id.value == "UPX-ORD-99"
    funds = gateway.get_funds()
    assert funds.balance.amount == Decimal("100000")

    assert any(c[0] == "GET" and "quote" in c[1] for c in transport.calls)
    assert any(c[0] == "POST" and "order" in c[1] for c in transport.calls)
    gateway.close()
