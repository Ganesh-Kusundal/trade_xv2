"""Upstox-only get_order fallback paths (no direct order_query)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.providers.upstox.adapters.order_gateway import OrderGateway
from brokers.providers.upstox.wire import UpstoxWireAdapter
from domain import OrderStatus
from tests.fixtures.domain_helpers import make_order


def _make_order(order_id: str = "ORD-789", status: OrderStatus = OrderStatus.OPEN):
    return make_order(order_id=order_id, status=status, order_type="MARKET", quantity=1)


@pytest.mark.unit
def test_get_order_fallback_when_no_order_query() -> None:
    broker = MagicMock(spec=["settings"])
    broker.settings = MagicMock(analytics_only=False, allow_live_orders=True)
    portfolio = MagicMock()
    portfolio.get_orderbook.return_value = [_make_order("ORD-789")]

    gw = UpstoxWireAdapter.__new__(UpstoxWireAdapter)
    gw._order_gw = OrderGateway(broker, MagicMock(), portfolio)

    result = gw.get_order("ORD-789")
    assert result is not None
    assert result.order_id == "ORD-789"


@pytest.mark.unit
def test_get_order_fallback_returns_none_if_not_in_orderbook() -> None:
    broker = MagicMock(spec=["settings"])
    broker.settings = MagicMock()
    portfolio = MagicMock()
    portfolio.get_orderbook.return_value = []

    gw = UpstoxWireAdapter.__new__(UpstoxWireAdapter)
    gw._order_gw = OrderGateway(broker, MagicMock(), portfolio)

    assert gw.get_order("NONEXISTENT") is None
