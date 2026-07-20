"""Canonical order command mapper parity."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms.order_command_mapper import (
    order_intent_to_oms_command,
    order_request_to_oms_command,
)
from domain import OrderType, ProductType, Side
from domain.orders.intent import OrderIntent
from domain.orders.requests import OrderRequest


@pytest.mark.unit
def test_order_request_to_oms_command_maps_side_and_price() -> None:
    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500.5"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        correlation_id="corr-abc",
    )
    cmd = order_request_to_oms_command(req)
    assert cmd.symbol == "RELIANCE"
    assert cmd.side is Side.BUY
    assert cmd.quantity == 10
    assert cmd.price == Decimal("2500.5")
    assert cmd.correlation_id == "corr-abc"


@pytest.mark.unit
def test_order_intent_to_oms_command_matches_request_fields() -> None:
    intent = OrderIntent(
        symbol="INFY",
        exchange="NSE",
        side=Side.SELL,
        quantity=5,
        price=Decimal("1500"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="intent-1",
    )
    cmd = order_intent_to_oms_command(intent)
    assert cmd.symbol == intent.symbol
    assert cmd.side is intent.side
    assert cmd.quantity == intent.quantity
    assert cmd.correlation_id == intent.correlation_id
