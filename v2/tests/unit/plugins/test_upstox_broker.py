"""Tests for Upstox broker plugin — Gateway, Wire, Orders adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from domain.commands import PlaceOrderCommand
from domain.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from domain.ports.broker_adapter import BrokerAdapter
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)
from plugins.brokers.upstox.connection import UpstoxConnection
from plugins.brokers.upstox.gateway import UpstoxGateway
from plugins.brokers.upstox.wire import UpstoxWire


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeTransport:
    """Mock transport that records calls and returns canned responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._responses: dict[str, Any] = {}

    def set_response(self, path: str, response: Any) -> None:
        self._responses[path] = response

    def get(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("GET", path, kwargs))
        return self._responses.get(path, {})

    def post(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("POST", path, kwargs))
        return self._responses.get(path, {})

    def put(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("PUT", path, kwargs))
        return self._responses.get(path, {})

    def delete(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("DELETE", path, kwargs))
        return self._responses.get(path, {})


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def wire() -> UpstoxWire:
    w = UpstoxWire()
    w.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    w.register_key(InstrumentId.parse("NSE:TCS"), "NSE_EQ:TCS")
    return w


@pytest.fixture
def connection(fake_transport: FakeTransport) -> UpstoxConnection:
    conn = UpstoxConnection(transport=fake_transport)
    conn.wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    return conn


@pytest.fixture
def gateway(fake_transport: FakeTransport) -> UpstoxGateway:
    from plugins.brokers.upstox.config import UpstoxConfig

    return UpstoxGateway(
        config=UpstoxConfig(allow_live_orders=True),  # test transport — safe to enable gate
        transport=fake_transport,
    )


def _sample_command() -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(Decimal("10")),
        price=Price(Decimal("2500.50")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=MagicMock()),
    )


# ---------------------------------------------------------------------------
# 1. Gateway satisfies BrokerAdapter protocol
# ---------------------------------------------------------------------------


class TestGatewayProtocol:
    def test_gateway_is_broker_adapter(self, gateway: UpstoxGateway) -> None:
        assert isinstance(gateway, BrokerAdapter)

    def test_gateway_has_all_required_methods(self, gateway: UpstoxGateway) -> None:
        required = [
            "submit_order",
            "cancel_order",
            "modify_order",
            "get_order",
            "get_orderbook",
            "get_positions",
            "get_funds",
            "mass_status",
        ]
        for method in required:
            assert hasattr(gateway, method), f"Missing method: {method}"


# ---------------------------------------------------------------------------
# 2. UpstoxWire.from_place_command
# ---------------------------------------------------------------------------


class TestWireFromPlaceCommand:
    def test_buy_limit_order(self, wire: UpstoxWire) -> None:
        # Register the instrument key mapping
        wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
        cmd = _sample_command()
        body = wire.from_place_command(cmd)
        assert body["instrument_token"] == "NSE_EQ:RELIANCE"
        assert body["transaction_type"] == "BUY"
        assert body["order_type"] == "LIMIT"
        assert body["quantity"] == 10
        assert body["price"] == 2500.50
        assert body["validity"] == "DAY"
        assert body["product"] == "I"

    def test_sell_market_order_no_price(self, wire: UpstoxWire) -> None:
        wire.register_key(InstrumentId.parse("NSE:TCS"), "NSE_EQ:TCS")
        cmd = PlaceOrderCommand(
            instrument_id=InstrumentId.parse("NSE:TCS"),
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Quantity(Decimal("5")),
            price=None,
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(value=MagicMock()),
        )
        body = wire.from_place_command(cmd)
        assert body["transaction_type"] == "SELL"
        assert body["order_type"] == "MARKET"
        assert body["quantity"] == 5
        assert "price" not in body


# ---------------------------------------------------------------------------
# 3. UpstoxWire.to_order_id
# ---------------------------------------------------------------------------


class TestWireToOrderId:
    def test_extracts_order_id_from_data(self, wire: UpstoxWire) -> None:
        native = {"data": {"order_id": "UPX-12345"}}
        oid = wire.to_order_id(native)
        assert oid == OrderId("UPX-12345")

    def test_extracts_from_top_level(self, wire: UpstoxWire) -> None:
        native = {"order_id": "UPX-67890"}
        oid = wire.to_order_id(native)
        assert oid == OrderId("UPX-67890")

    def test_raises_on_missing_order_id(self, wire: UpstoxWire) -> None:
        with pytest.raises(ValueError, match="order_id"):
            wire.to_order_id({"data": {}})


# ---------------------------------------------------------------------------
# 4. UpstoxWire.to_order
# ---------------------------------------------------------------------------


class TestWireToOrder:
    def test_converts_full_order(self, wire: UpstoxWire) -> None:
        native = {
            "order_id": "UPX-100",
            "instrument_token": "NSE_EQ:RELIANCE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 10,
            "price": 2500.0,
            "status": "complete",
            "filled_quantity": 10,
            "tag": "test-corr-id",
        }
        order = wire.to_order(native)
        assert order.order_id == OrderId("UPX-100")
        assert order.instrument_id == InstrumentId.parse("NSE:RELIANCE")
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == Quantity(Decimal("10"))
        assert order.price == Price(Decimal("2500.0"))
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Quantity(Decimal("10"))

    def test_converts_open_order(self, wire: UpstoxWire) -> None:
        native = {
            "order_id": "UPX-200",
            "instrument_token": "NSE_EQ:TCS",
            "transaction_type": "SELL",
            "order_type": "MARKET",
            "quantity": 5,
            "price": 0,
            "status": "open",
        }
        order = wire.to_order(native)
        assert order.status == OrderStatus.SUBMITTED
        assert order.price is None  # price=0 treated as None


# ---------------------------------------------------------------------------
# 5. UpstoxWire.to_account
# ---------------------------------------------------------------------------


class TestWireToAccount:
    def test_converts_funds(self, wire: UpstoxWire) -> None:
        native = {
            "data": {
                "equity": {
                    "available_margin": 50000.0,
                }
            }
        }
        account = wire.to_account(native)
        assert account.account_id == AccountId("upstox")
        assert account.balance == Money(amount=Decimal("50000.0"), currency="INR")


# ---------------------------------------------------------------------------
# 6. UpstoxWire.to_position
# ---------------------------------------------------------------------------


class TestWireToPosition:
    def test_converts_position(self, wire: UpstoxWire) -> None:
        native = {
            "instrument_token": "NSE_EQ:RELIANCE",
            "quantity": 10,
            "average_price": 2500.0,
            "realised": 150.0,
            "unrealised": 200.0,
        }
        pos = wire.to_position(native)
        assert pos.instrument_id == InstrumentId.parse("NSE:RELIANCE")
        assert pos.quantity == Quantity(Decimal("10"))
        assert pos.avg_price == Price(Decimal("2500.0"))
        assert pos.realized_pnl == Money(amount=Decimal("150.0"), currency="INR")
        assert pos.unrealized_pnl == Money(amount=Decimal("200.0"), currency="INR")


# ---------------------------------------------------------------------------
# 7. place_order sends correct HTTP request
# ---------------------------------------------------------------------------


class TestOrdersAdapterPlaceOrder:
    def test_place_order_calls_post(
        self, connection: UpstoxConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/order/place", {"data": {"order_id": "UPX-NEW-1"}}
        )
        # Register instrument key so wire can resolve
        connection.wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
        cmd = _sample_command()
        oid = connection.orders.place_order(cmd)
        assert oid == OrderId("UPX-NEW-1")
        # Verify POST was called
        post_calls = [c for c in fake_transport.calls if c[0] == "POST"]
        assert len(post_calls) == 1
        assert post_calls[0][1] == "/order/place"
        body = post_calls[0][2].get("json", {})
        assert body["instrument_token"] == "NSE_EQ:RELIANCE"
        assert body["transaction_type"] == "BUY"

    def test_place_order_stores_in_cache(
        self, connection: UpstoxConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/order/place", {"data": {"order_id": "UPX-CACHE-1"}}
        )
        connection.wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
        cmd = _sample_command()
        oid = connection.orders.place_order(cmd)
        assert oid.value in connection.orders._cache


# ---------------------------------------------------------------------------
# 8. cancel_order sends correct HTTP request
# ---------------------------------------------------------------------------


class TestOrdersAdapterCancelOrder:
    def test_cancel_order_calls_delete(
        self, connection: UpstoxConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response("/order/cancel", {})
        oid = OrderId("UPX-CANCEL-1")
        connection.orders.cancel_order(oid)
        delete_calls = [c for c in fake_transport.calls if c[0] == "DELETE"]
        assert len(delete_calls) == 1
        assert delete_calls[0][1] == "/order/cancel"


# ---------------------------------------------------------------------------
# 9. get_order calls correct endpoint
# ---------------------------------------------------------------------------


class TestOrdersAdapterGetOrder:
    def test_get_order_calls_get(
        self, connection: UpstoxConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/order/history",
            {
                "data": [
                    {
                        "order_id": "UPX-HIST-1",
                        "instrument_token": "NSE_EQ:RELIANCE",
                        "transaction_type": "BUY",
                        "order_type": "LIMIT",
                        "quantity": 10,
                        "price": 2500.0,
                        "status": "complete",
                        "filled_quantity": 10,
                    }
                ]
            },
        )
        oid = OrderId("UPX-HIST-1")
        order = connection.orders.get_order(oid)
        assert order.order_id == OrderId("UPX-HIST-1")
        assert order.status == OrderStatus.FILLED
        get_calls = [c for c in fake_transport.calls if c[0] == "GET"]
        assert any("/order/history" in c[1] for c in get_calls)


# ---------------------------------------------------------------------------
# 10. Gateway delegates to connection
# ---------------------------------------------------------------------------


class TestGatewayDelegation:
    def test_submit_order_delegates(
        self, gateway: UpstoxGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/order/place", {"data": {"order_id": "UPX-GW-1"}}
        )
        gateway.connection.wire.register_key(
            InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE"
        )
        cmd = _sample_command()
        oid = gateway.submit_order(cmd)
        assert oid == OrderId("UPX-GW-1")

    def test_cancel_order_delegates(
        self, gateway: UpstoxGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response("/order/cancel", {})
        gateway.cancel_order(OrderId("UPX-GW-2"))
        delete_calls = [c for c in fake_transport.calls if c[0] == "DELETE"]
        assert len(delete_calls) == 1
