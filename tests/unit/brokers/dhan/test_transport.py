"""Unit + contract tests for the Dhan broker transport plugin."""

from __future__ import annotations

from tests.support.order_request_factory import make_order_request as _order_request

from decimal import Decimal

from brokers.providers.dhan.api.transport import _DHAN_CAPABILITIES, DhanTransport
from domain.capabilities import Capability
from domain.orders.requests import OrderRequest
from domain.types import OrderType, ProductType, Side


class _FakeResponse:
    def __init__(self, success: bool = True, error: str = "") -> None:
        self.success = success
        self.error = error
        self.order_id = "O1"


class FakeGateway:
    """Records calls and returns harmless fakes — no network."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def place_order(self, request: OrderRequest):
        side = getattr(request.transaction_type, "value", request.transaction_type)
        order_type = getattr(request.order_type, "value", request.order_type)
        product_type = getattr(request.product_type, "value", request.product_type)
        self.calls.append(
            (
                "place_order",
                request.symbol,
                request.exchange,
                side,
                request.quantity,
                order_type,
                product_type,
            )
        )
        return _FakeResponse()

    def cancel_order(self, order_id):
        return _FakeResponse()

    def modify_order(self, order_id, **changes):
        return _FakeResponse()

    def get_orderbook(self):
        return []

    def positions(self):
        return []

    def holdings(self):
        return []

    def funds(self):
        return None

    def close(self):
        self.calls.append(("close",))


def _transport() -> DhanTransport:
    # DhanDataAdapter(gateway) only stores the gateway; no network at construction.
    return DhanTransport(FakeGateway())


def test_dhan_transport_is_broker_transport():
    t = _transport()
    assert hasattr(t, "name")
    assert hasattr(t, "market_data")
    assert hasattr(t, "execution")
    assert hasattr(t, "capabilities")
    assert hasattr(t, "close")


def test_dhan_transport_identity_and_capabilities():
    t = _transport()
    assert t.name == "dhan"
    assert t.capabilities() == list(_DHAN_CAPABILITIES)
    assert t.supports(Capability.OPTION_GREEKS) is True
    assert t.supports(Capability.GLOBAL_MARKETS) is False


def test_dhan_transport_execution_maps_order_request():
    gw = FakeGateway()
    t = DhanTransport(gw)
    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
    )
    res = t.execution.place_order(req)
    assert res.success is True
    assert gw.calls[0][0] == "place_order"
    # mapped args: symbol, exchange, side, quantity, order_type, product_type
    assert gw.calls[0][1] == "RELIANCE"
    assert gw.calls[0][3] == "BUY"
    assert gw.calls[0][4] == 10
    assert gw.calls[0][5] == "LIMIT"


def test_dhan_transport_close_tears_down_gateway():
    gw = FakeGateway()
    t = DhanTransport(gw)
    t.close()
    assert ("close",) in gw.calls


def test_dhan_transport_satisfies_shared_contract():
    # Reuse the domain's BrokerAdapter contract on the real plugin.
    from tests.unit.domain.test_broker_transport_contract import (
        _BrokerAdapterContract,
    )

    class _Contract(_BrokerAdapterContract):
        def build_transport(self):
            return _transport()

    c = _Contract()
    c.test_name_present()
    c.test_execution_is_execution_provider()
    c.test_capabilities_are_domain_enum()
    c.test_supports_discovery()
    c.test_execution_roundtrip()
    # market_data is the gateway duck-type until a real DataProvider adapter is wired;
    # execution port is the critical contract for OMS (Wave C).
    assert _transport().market_data is not None
    assert isinstance(_transport().execution, type(_transport().execution))
