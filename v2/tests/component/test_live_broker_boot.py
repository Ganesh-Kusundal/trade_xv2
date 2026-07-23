"""LIVE RuntimeFactory + boot with injectable fake gateway (no real money)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from config.schema import AppConfig, Environment
from domain.commands import PlaceOrderCommand
from domain.enums import BrokerId, OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Quantity
from runtime.factory import RuntimeFactory
from runtime.startup import boot
from shared.errors import LifecycleError


class _LiveFakeGateway:
    def __init__(self, *, auth_ok: bool = True) -> None:
        self.auth_ok = auth_ok
        self.connected = False
        self.loaded = False

    def connect(self) -> None:
        self.connected = True

    def authenticate(self) -> bool:
        return self.auth_ok

    def load_instruments(self) -> None:
        self.loaded = True

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return OrderId(value="FAKE-LIVE-1")

    def get_order(self, order_id: OrderId):
        from domain.entities import Order

        o = Order(
            order_id=order_id,
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(value=Decimal("1")),
            price=None,
            time_in_force=TimeInForce.DAY,
            status=OrderStatus.PENDING,
            correlation_id=CorrelationId(value=uuid4()),
        )
        o = o.transition_to(OrderStatus.SUBMITTED)
        return o

    def cancel_order(self, order_id: OrderId) -> None:
        return None


def test_live_boot_requires_authenticate() -> None:
    cfg = AppConfig(environment=Environment.LIVE, broker=BrokerId.DHAN)
    rt = RuntimeFactory.build(cfg, broker_adapter=_LiveFakeGateway(auth_ok=False))
    with pytest.raises(LifecycleError, match="authenticate"):
        boot(rt)


def test_live_boot_and_submit_returns_submitted() -> None:
    cfg = AppConfig(environment=Environment.LIVE, broker=BrokerId.DHAN)
    gw = _LiveFakeGateway(auth_ok=True)
    rt = RuntimeFactory.build(cfg, broker_adapter=gw)
    rt = boot(rt)
    assert rt.environment_frozen
    assert gw.connected and gw.loaded
    cmd = PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    order = rt.fill_source.submit(cmd)
    assert order.status is OrderStatus.SUBMITTED
    assert order.order_id.value == "FAKE-LIVE-1"
