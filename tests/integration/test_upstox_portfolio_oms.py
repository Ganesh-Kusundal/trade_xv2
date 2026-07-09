"""Upstox portfolio stream integration with OMS handlers."""

from __future__ import annotations
from tests.conftest import build_test_trading_context

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from application.oms import create_trading_context
from brokers.upstox.tests.unit.test_websocket_safety import _fake_authorizer, _FakeSocket
from brokers.upstox.websocket.portfolio_stream import UpstoxPortfolioStream
from domain import Order, OrderStatus, OrderType, ProductType, Side


@pytest.mark.asyncio
async def test_upstox_portfolio_stream_updates_oms_position():
    """ORDER_UPDATED + TRADE from Upstox WS must flow through OMS to positions."""
    ctx = build_test_trading_context(replay_events=False)
    seed = Order(
        order_id="O1",
        symbol="INFY",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        filled_quantity=0,
        price=Decimal("1500"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
    )
    ctx.order_manager.upsert_order(seed)

    stream = UpstoxPortfolioStream(
        authorizer=_fake_authorizer(),
        socket_factory=lambda _url: _FakeSocket(
            [
                '{"type":"order","data":{"order_id":"O1","trading_symbol":"INFY","exchange":"NSE","transaction_type":"BUY","quantity":100,"filled_quantity":100,"average_price":"1500","order_type":"MARKET","product":"I","validity":"DAY","status":"complete"}}',
            ]
        ),
        event_bus=ctx.event_bus,
    )
    await stream.connect()
    await asyncio.sleep(0.15)
    await stream.disconnect()

    positions = ctx.position_manager.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "INFY"
    assert positions[0].quantity == 100
