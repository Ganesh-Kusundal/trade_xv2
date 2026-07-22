"""AdapterTestHarness against real PaperGateway — no mocks, no network."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.commands import PlaceOrderCommand
from domain.entities import Order, Quote
from domain.enums import BrokerId, OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import (
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)
from plugins.brokers.paper import register
from plugins.brokers.paper.gateway import PaperGateway
from plugins.brokers.paper.wire import PaperWire
from plugins.brokers.registry import get_plugin, list_plugins
from tests.integration.adapter_harness import AdapterTestHarness

_INSTR = InstrumentId(value="NSE:RELIANCE")


def _seed_quote(gateway: PaperGateway) -> Quote:
    quote = Quote(
        instrument_id=_INSTR,
        bid=Price(value=Decimal("2499")),
        ask=Price(value=Decimal("2501")),
        bid_size=Quantity(value=Decimal("100")),
        ask_size=Quantity(value=Decimal("100")),
        timestamp=datetime.now(UTC),
    )
    gateway.connection.set_quote(quote)
    return quote


@pytest.fixture
def gateway() -> PaperGateway:
    gw = PaperGateway(starting_cash=Money(amount=Decimal("1_000_000"), currency="INR"))
    gw.connect()
    _seed_quote(gw)
    yield gw
    gw.close()


def test_register_paper_broker_id() -> None:
    register()
    assert BrokerId.PAPER in list_plugins()
    plugin = get_plugin(BrokerId.PAPER)
    assert plugin["gateway"] is PaperGateway
    register()  # idempotent overwrite


def test_harness_connect_quote_place_positions_funds_mass_status(gateway: PaperGateway) -> None:
    harness = AdapterTestHarness(adapter=gateway)

    harness.test_connect()
    gateway.connect()
    _seed_quote(gateway)

    quote = harness.test_get_quote(_INSTR)
    assert quote.bid.value == Decimal("2499")

    cmd = PlaceOrderCommand(
        instrument_id=_INSTR,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("10")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    order_id = harness.test_place_fill(cmd)

    positions = harness.test_get_positions()
    assert len(positions) == 1
    assert positions[0].instrument_id == _INSTR
    assert positions[0].quantity.value == Decimal("10")
    # market fill at mid (2499+2501)/2 = 2500
    assert positions[0].avg_price.value == Decimal("2500")

    funds = harness.test_get_funds()
    assert funds.balance.amount == Decimal("1_000_000") - Decimal("2500") * Decimal("10")

    snap = harness.test_mass_status()
    orders = getattr(snap, "orders", None) or snap["orders"]
    assert any(o.order_id == order_id and o.status == OrderStatus.FILLED for o in orders)

    caps = harness.test_capabilities()
    assert getattr(caps, "supports_market_orders", True) is True


def test_place_limit_fills_at_limit_price(gateway: PaperGateway) -> None:
    cmd = PlaceOrderCommand(
        instrument_id=_INSTR,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("2")),
        price=Price(value=Decimal("2490")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    gateway.place_order(cmd)
    pos = gateway.get_positions()[0]
    assert pos.avg_price.value == Decimal("2490")


def test_cancel_rejects_filled_order(gateway: PaperGateway) -> None:
    cmd = PlaceOrderCommand(
        instrument_id=_INSTR,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    oid = gateway.place_order(cmd)
    with pytest.raises(ValueError):
        gateway.cancel_order(oid)


def test_get_quote_without_seed_raises(gateway: PaperGateway) -> None:
    missing = InstrumentId(value="NSE:UNKNOWN")
    with pytest.raises(KeyError):
        gateway.get_quote(missing)


def test_wire_roundtrip_identity() -> None:
    wire = PaperWire()
    quote = Quote(
        instrument_id=_INSTR,
        bid=Price(value=Decimal("10")),
        ask=Price(value=Decimal("11")),
        bid_size=Quantity(value=Decimal("1")),
        ask_size=Quantity(value=Decimal("1")),
        timestamp=datetime.now(UTC),
    )
    assert wire.to_quote(quote) is quote
    assert wire.from_quote(quote) is quote

    order = Order(
        order_id=OrderId(value="p-1"),
        instrument_id=_INSTR,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        status=OrderStatus.FILLED,
        correlation_id=CorrelationId(value=uuid4()),
    )
    assert wire.to_order(order) is order
    assert wire.from_order(order) is order
