"""C0.7a — DhanBrokerGateway exposes get_order."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
def test_gateway_get_order_delegates_to_orders_adapter() -> None:
    from brokers.dhan.gateway import DhanBrokerGateway

    # Build a minimal gateway shell if constructor is heavy — patch connection.
    orders = MagicMock()
    expected = MagicMock(name="Order")
    orders.get_order.return_value = expected
    conn = MagicMock()
    conn.orders = orders

    # Prefer lightweight construction
    gw = object.__new__(DhanBrokerGateway)
    gw._conn = conn  # noqa: SLF001

    got = gw.get_order("12345")
    orders.get_order.assert_called_once_with("12345")
    assert got is expected
