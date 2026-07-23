"""Live-order safety gate — place_order must refuse unless allow_live_orders=True.

Mirrors the legacy guard in src/brokers/providers/dhan/execution/order_placement.py.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Quantity
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.gateway import DhanGateway
from plugins.brokers.upstox.config import UpstoxConfig
from plugins.brokers.upstox.gateway import UpstoxGateway


@pytest.fixture()
def command() -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(uuid4()),
    )


class _StubOrders:
    """Records whether place_order ever reached the broker adapter."""

    def __init__(self) -> None:
        self.called = False

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        self.called = True
        return OrderId("stub-order-id")


# ---------------------------------------------------------------------------
# Config defaults / env override
# ---------------------------------------------------------------------------

class TestConfigFlag:
    def test_dhan_defaults_to_disabled(self) -> None:
        assert DhanConfig().allow_live_orders is False

    def test_upstox_defaults_to_disabled(self) -> None:
        assert UpstoxConfig().allow_live_orders is False

    def test_dhan_from_env_default_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DHAN_ALLOW_LIVE_ORDERS", raising=False)
        assert DhanConfig.from_env().allow_live_orders is False

    def test_upstox_from_env_default_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UPSTOX_ALLOW_LIVE_ORDERS", raising=False)
        assert UpstoxConfig.from_env().allow_live_orders is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_dhan_from_env_enabled(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("DHAN_ALLOW_LIVE_ORDERS", value)
        assert DhanConfig.from_env().allow_live_orders is True

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_upstox_from_env_enabled(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("UPSTOX_ALLOW_LIVE_ORDERS", value)
        assert UpstoxConfig.from_env().allow_live_orders is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
    def test_dhan_from_env_falsey_values_stay_disabled(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("DHAN_ALLOW_LIVE_ORDERS", value)
        assert DhanConfig.from_env().allow_live_orders is False


# ---------------------------------------------------------------------------
# Gateway gate
# ---------------------------------------------------------------------------

class TestDhanGate:
    def test_place_order_raises_when_disabled(self, command: PlaceOrderCommand) -> None:
        gateway = DhanGateway(config=DhanConfig())
        stub = _StubOrders()
        gateway.connection.orders = stub  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="Live orders disabled"):
            gateway.place_order(command)
        assert stub.called is False

    def test_submit_order_raises_when_disabled(self, command: PlaceOrderCommand) -> None:
        gateway = DhanGateway(config=DhanConfig())
        stub = _StubOrders()
        gateway.connection.orders = stub  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="allow_live_orders"):
            gateway.submit_order(command)
        assert stub.called is False

    def test_place_order_allowed_when_enabled(self, command: PlaceOrderCommand) -> None:
        gateway = DhanGateway(config=DhanConfig(allow_live_orders=True))
        stub = _StubOrders()
        gateway.connection.orders = stub  # type: ignore[assignment]
        assert gateway.place_order(command) == OrderId("stub-order-id")
        assert stub.called is True


class TestUpstoxGate:
    def test_place_order_raises_when_disabled(self, command: PlaceOrderCommand) -> None:
        gateway = UpstoxGateway(config=UpstoxConfig())
        stub = _StubOrders()
        gateway.connection.orders = stub  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="Live orders disabled"):
            gateway.place_order(command)
        assert stub.called is False

    def test_submit_order_raises_when_disabled(self, command: PlaceOrderCommand) -> None:
        gateway = UpstoxGateway(config=UpstoxConfig())
        stub = _StubOrders()
        gateway.connection.orders = stub  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="allow_live_orders"):
            gateway.submit_order(command)
        assert stub.called is False

    def test_place_order_allowed_when_enabled(self, command: PlaceOrderCommand) -> None:
        gateway = UpstoxGateway(config=UpstoxConfig(allow_live_orders=True))
        stub = _StubOrders()
        gateway.connection.orders = stub  # type: ignore[assignment]
        assert gateway.place_order(command) == OrderId("stub-order-id")
        assert stub.called is True
