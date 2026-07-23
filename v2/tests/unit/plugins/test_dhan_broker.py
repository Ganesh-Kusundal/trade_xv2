"""Tests for Dhan broker plugin — Gateway, Wire, Orders adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Order, Position
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
from plugins.brokers.dhan.connection import DhanConnection
from plugins.brokers.dhan.gateway import DhanGateway
from plugins.brokers.dhan.wire import DhanWire


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
def wire() -> DhanWire:
    w = DhanWire()
    w.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    w.register_security(InstrumentId.parse("NSE:TCS"), "11536")
    return w


@pytest.fixture
def connection(fake_transport: FakeTransport) -> DhanConnection:
    conn = DhanConnection(transport=fake_transport)
    conn.wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    return conn


@pytest.fixture
def gateway(fake_transport: FakeTransport) -> DhanGateway:
    from plugins.brokers.dhan.config import DhanConfig

    gw = DhanGateway(
        config=DhanConfig(allow_live_orders=True),  # test transport — safe to enable gate
        transport=fake_transport,
    )
    gw.connection.wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    return gw


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
    def test_gateway_is_broker_adapter(self, gateway: DhanGateway) -> None:
        assert isinstance(gateway, BrokerAdapter)

    def test_gateway_has_all_required_methods(self, gateway: DhanGateway) -> None:
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
# 2. DhanWire.from_place_command
# ---------------------------------------------------------------------------


class TestWireFromPlaceCommand:
    def test_buy_limit_order(self, wire: DhanWire) -> None:
        cmd = _sample_command()
        body = wire.from_place_command(cmd)
        assert body["securityId"] == "2885"
        assert body["transactionType"] == "BUY"
        assert body["orderType"] == "LIMIT"
        assert body["quantity"] == 10
        assert body["price"] == 2500.50
        assert body["validity"] == "DAY"
        assert body["productType"] == "INTRADAY"

    def test_sell_market_order_no_price(self, wire: DhanWire) -> None:
        cmd = PlaceOrderCommand(
            instrument_id=InstrumentId.parse("NSE:TCS"),
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Quantity(Decimal("5")),
            price=None,
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(value=MagicMock()),
        )
        wire.register_security(InstrumentId.parse("NSE:TCS"), "11536")
        body = wire.from_place_command(cmd)
        assert body["transactionType"] == "SELL"
        assert body["orderType"] == "MARKET"
        assert body["quantity"] == 5
        assert "price" not in body


# ---------------------------------------------------------------------------
# 3. DhanWire.to_order_id
# ---------------------------------------------------------------------------


class TestWireToOrderId:
    def test_extracts_order_id_from_data(self, wire: DhanWire) -> None:
        native = {"orderId": "DHAN-12345"}
        oid = wire.to_order_id(native)
        assert oid == OrderId("DHAN-12345")

    def test_extracts_from_nested_data(self, wire: DhanWire) -> None:
        native = {"data": {"orderId": "DHAN-67890"}}
        oid = wire.to_order_id(native)
        assert oid == OrderId("DHAN-67890")

    def test_raises_on_missing_order_id(self, wire: DhanWire) -> None:
        with pytest.raises(ValueError, match="orderId"):
            wire.to_order_id({"data": {}})


# ---------------------------------------------------------------------------
# 4. DhanWire.to_order
# ---------------------------------------------------------------------------


class TestWireToOrder:
    def test_converts_full_order(self, wire: DhanWire) -> None:
        native = {
            "orderId": "DHAN-100",
            "securityId": "2885",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "quantity": 10,
            "price": 2500.0,
            "orderStatus": "TRADED",
            "filledQty": 10,
            "correlationId": "test-corr-id",
        }
        order = wire.to_order(native)
        assert order.order_id == OrderId("DHAN-100")
        assert order.instrument_id == InstrumentId.parse("NSE:RELIANCE")
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == Quantity(Decimal("10"))
        assert order.price == Price(Decimal("2500.0"))
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == Quantity(Decimal("10"))

    def test_converts_pending_order(self, wire: DhanWire) -> None:
        native = {
            "orderId": "DHAN-200",
            "securityId": "11536",
            "transactionType": "SELL",
            "orderType": "MARKET",
            "quantity": 5,
            "price": 0,
            "orderStatus": "TRANSIT",
        }
        order = wire.to_order(native)
        assert order.status == OrderStatus.SUBMITTED
        assert order.price is None  # price=0 treated as None

    def test_converts_rejected_order(self, wire: DhanWire) -> None:
        native = {
            "orderId": "DHAN-300",
            "securityId": "2885",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "quantity": 10,
            "price": 2500.0,
            "orderStatus": "REJECTED",
        }
        order = wire.to_order(native)
        assert order.status == OrderStatus.REJECTED


# ---------------------------------------------------------------------------
# 5. DhanWire.to_account
# ---------------------------------------------------------------------------


class TestWireToAccount:
    def test_converts_funds(self, wire: DhanWire) -> None:
        native = {
            "availabelBalance": 50000.0,
            "utilizedMargin": 10000.0,
        }
        account = wire.to_account(native)
        assert account.account_id == AccountId("dhan")
        assert account.balance == Money(amount=Decimal("50000.0"), currency="INR")
        assert account.margin == Money(amount=Decimal("10000.0"), currency="INR")


# ---------------------------------------------------------------------------
# 6. DhanWire.to_position
# ---------------------------------------------------------------------------


class TestWireToPosition:
    def test_converts_position(self, wire: DhanWire) -> None:
        native = {
            "securityId": "2885",
            "netQty": 10,
            "avgCostPrice": 2500.0,
            "realizedProfit": 150.0,
            "unrealizedProfit": 200.0,
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
        self, connection: DhanConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/orders", {"orderId": "DHAN-NEW-1"}
        )
        cmd = _sample_command()
        oid = connection.orders.place_order(cmd)
        assert oid == OrderId("DHAN-NEW-1")
        # Verify POST was called
        post_calls = [c for c in fake_transport.calls if c[0] == "POST"]
        assert len(post_calls) == 1
        assert post_calls[0][1] == "/orders"
        body = post_calls[0][2].get("json", {})
        assert body["securityId"] == "2885"
        assert body["transactionType"] == "BUY"

    def test_place_order_stores_in_cache(
        self, connection: DhanConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/orders", {"orderId": "DHAN-CACHE-1"}
        )
        cmd = _sample_command()
        oid = connection.orders.place_order(cmd)
        assert oid.value in connection.orders._cache


# ---------------------------------------------------------------------------
# 8. cancel_order sends correct HTTP request
# ---------------------------------------------------------------------------


class TestOrdersAdapterCancelOrder:
    def test_cancel_order_calls_post(
        self, connection: DhanConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response("/orders/DHAN-CANCEL-1/cancel", {})
        oid = OrderId("DHAN-CANCEL-1")
        connection.orders.cancel_order(oid)
        post_calls = [c for c in fake_transport.calls if c[0] == "POST"]
        assert len(post_calls) == 1
        assert "/orders/DHAN-CANCEL-1/cancel" in post_calls[0][1]


# ---------------------------------------------------------------------------
# 9. get_order calls correct endpoint
# ---------------------------------------------------------------------------


class TestOrdersAdapterGetOrder:
    def test_get_order_calls_get(
        self, connection: DhanConnection, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/orders/DHAN-HIST-1",
            {
                "orderId": "DHAN-HIST-1",
                "securityId": "2885",
                "transactionType": "BUY",
                "orderType": "LIMIT",
                "quantity": 10,
                "price": 2500.0,
                "orderStatus": "TRADED",
                "filledQty": 10,
            },
        )
        oid = OrderId("DHAN-HIST-1")
        order = connection.orders.get_order(oid)
        assert order.order_id == OrderId("DHAN-HIST-1")
        assert order.status == OrderStatus.FILLED
        get_calls = [c for c in fake_transport.calls if c[0] == "GET"]
        assert any("/orders/DHAN-HIST-1" in c[1] for c in get_calls)


# ---------------------------------------------------------------------------
# 10. Gateway delegates to connection
# ---------------------------------------------------------------------------


class TestGatewayDelegation:
    def test_submit_order_delegates(
        self, gateway: DhanGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/orders", {"orderId": "DHAN-GW-1"}
        )
        cmd = _sample_command()
        oid = gateway.submit_order(cmd)
        assert oid == OrderId("DHAN-GW-1")

    def test_cancel_order_delegates(
        self, gateway: DhanGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response("/orders/DHAN-GW-2/cancel", {})
        gateway.cancel_order(OrderId("DHAN-GW-2"))
        post_calls = [c for c in fake_transport.calls if c[0] == "POST"]
        assert len(post_calls) == 1

    def test_get_order_delegates(
        self, gateway: DhanGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/orders/DHAN-GW-3",
            {
                "orderId": "DHAN-GW-3",
                "securityId": "2885",
                "transactionType": "BUY",
                "orderType": "LIMIT",
                "quantity": 10,
                "price": 2500.0,
                "orderStatus": "PENDING",
            },
        )
        order = gateway.get_order(OrderId("DHAN-GW-3"))
        assert order.order_id == OrderId("DHAN-GW-3")
        assert order.status in (OrderStatus.SUBMITTED, OrderStatus.PENDING)

    def test_get_orderbook_delegates(
        self, gateway: DhanGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/orders",
            [
                {
                    "orderId": "DHAN-OB-1",
                    "securityId": "2885",
                    "transactionType": "BUY",
                    "orderType": "LIMIT",
                    "quantity": 10,
                    "price": 2500.0,
                    "orderStatus": "TRADED",
                    "filledQty": 10,
                }
            ],
        )
        orders = gateway.get_orderbook()
        assert len(orders) == 1
        assert orders[0].order_id == OrderId("DHAN-OB-1")

    def test_get_positions_delegates(
        self, gateway: DhanGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/positions",
            [
                {
                    "securityId": "2885",
                    "netQty": 10,
                    "avgCostPrice": 2500.0,
                    "realizedProfit": 0.0,
                    "unrealizedProfit": 100.0,
                }
            ],
        )
        positions = gateway.get_positions()
        assert len(positions) == 1
        assert positions[0].instrument_id == InstrumentId.parse("NSE:RELIANCE")

    def test_get_funds_delegates(
        self, gateway: DhanGateway, fake_transport: FakeTransport
    ) -> None:
        fake_transport.set_response(
            "/fundlimit",
            {"availabelBalance": 75000.0, "utilizedMargin": 5000.0},
        )
        account = gateway.get_funds()
        assert account.account_id == AccountId("dhan")
        assert account.balance == Money(amount=Decimal("75000.0"), currency="INR")
