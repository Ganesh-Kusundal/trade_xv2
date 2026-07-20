"""Paper resting limit orders fill when EventBus TICK crosses limit price."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.paper.paper_gateway import PaperGateway
from domain import OrderStatus, Side
from domain.constants import DEFAULT_EXCHANGE
from domain.entities.market import Quote
from domain.events.types import DomainEvent
from domain.ports.time_service import get_current_clock
from infrastructure.event_bus import EventBus, EventType
from runtime.live_datalake_wiring import wire_paper_limit_fills
from tests.unit.brokers.paper.conftest import MockPaperOrderManager


def _publish_tick(
    bus: EventBus,
    *,
    symbol: str,
    ltp: Decimal,
    exchange: str = DEFAULT_EXCHANGE,
) -> None:
    now = get_current_clock().now()
    quote = Quote(symbol=symbol, ltp=ltp, volume=0, timestamp=now)
    bus.publish(
        DomainEvent(
            event_type=EventType.TICK,
            timestamp=now,
            symbol=symbol,
            source="test",
            payload={
                "quote": quote,
                "exchange": exchange,
                "ltp": ltp,
                "timestamp": now,
            },
        )
    )


@pytest.fixture
def paper_setup():
    import runtime.live_datalake_wiring as ldw

    ldw._paper_fill_wired = False
    om = MockPaperOrderManager()
    gw = PaperGateway(order_manager=om)
    bus = EventBus()
    wire_paper_limit_fills(bus, gw.orders)
    return gw, bus, om


def test_buy_limit_fills_when_ltp_crosses(paper_setup) -> None:
    gw, bus, om = paper_setup

    order = gw.orders.place_order(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("95"),
        order_type="LIMIT",
    )
    assert order.status == OrderStatus.OPEN

    _publish_tick(bus, symbol="RELIANCE", ltp=Decimal("95"))
    filled = gw.get_order(order.order_id)
    assert filled is not None
    assert filled.status == OrderStatus.FILLED
    assert filled.avg_price is not None
    assert float(filled.avg_price) == 95.0
    assert len(gw.get_trade_book()) == 1
    assert len(om._trades) == 1


def test_sell_limit_fills_when_ltp_crosses(paper_setup) -> None:
    gw, bus, _om = paper_setup

    order = gw.orders.place_order(
        symbol="INFY",
        exchange="NSE",
        side=Side.SELL,
        quantity=5,
        price=Decimal("1510"),
        order_type="LIMIT",
    )
    assert order.status == OrderStatus.OPEN

    _publish_tick(bus, symbol="INFY", ltp=Decimal("1510"))
    filled = gw.get_order(order.order_id)
    assert filled is not None
    assert filled.status == OrderStatus.FILLED


def test_buy_limit_stays_open_when_ltp_above_limit(paper_setup) -> None:
    gw, bus, _om = paper_setup

    order = gw.orders.place_order(
        symbol="TCS",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("3900"),
        order_type="LIMIT",
    )
    assert order.status == OrderStatus.OPEN

    _publish_tick(bus, symbol="TCS", ltp=Decimal("3950"))
    still_open = gw.get_order(order.order_id)
    assert still_open is not None
    assert still_open.status == OrderStatus.OPEN
    assert gw.get_trade_book() == []
