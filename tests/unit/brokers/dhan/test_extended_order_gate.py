"""P1-T2 (drift D3): extended-order executors honour the live-order authority.

The super/forever/exit-all executors reach the broker wire directly, bypassing
the OMS normal-order gate. Each now accepts an ``authorize`` callable and MUST
call it before any wire call, so a blocked authority stops the order before it
leaves the process. These tests use the real ``FakeHttpClient`` (a recording
protocol fake, not a mock) to assert the wire was never touched on block.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.dhan.domain import ForeverOrderRequest
from brokers.dhan.execution.exit_all import ExitAllAdapter
from brokers.dhan.execution.forever_orders import ForeverOrdersAdapter
from brokers.dhan.execution.super_orders import SuperOrdersAdapter


class _Blocked(RuntimeError):
    """Stand-in for a LiveBrokerBlockedError / RiskRejectedError."""


def _block() -> None:
    raise _Blocked("authority refused")


def test_super_order_blocked_before_wire(fake_client, resolver):
    fake_client.set_response("POST", "/super/orders", {"data": {"orderId": "SO1"}})
    adapter = SuperOrdersAdapter(fake_client, resolver)
    with pytest.raises(_Blocked):
        adapter.place_super_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            price=Decimal("2450"),
            target_price=Decimal("2500"),
            stop_loss_price=Decimal("2400"),
            trailing_jump=Decimal("5"),
            authorize=_block,
        )
    assert fake_client.calls_for("POST", "/super/orders") == []


def test_super_order_reaches_wire_when_authorized(fake_client, resolver):
    fake_client.set_response("POST", "/super/orders", {"data": {"orderId": "SO1"}})
    adapter = SuperOrdersAdapter(fake_client, resolver)
    adapter.place_super_order(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=10,
        price=Decimal("2450"),
        target_price=Decimal("2500"),
        stop_loss_price=Decimal("2400"),
        trailing_jump=Decimal("5"),
        authorize=lambda: None,
    )
    assert len(fake_client.calls_for("POST", "/super/orders")) == 1


def test_forever_order_blocked_before_wire(fake_client, resolver):
    fake_client.set_response("POST", "/forever/orders", {"data": {"orderId": "FO1"}})
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    request = ForeverOrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        order_flag="SINGLE",
        transaction_type="BUY",
        product_type="CNC",
        order_type="LIMIT",
        quantity=10,
        price=Decimal("2450"),
        trigger_price=Decimal("2460"),
    )
    with pytest.raises(_Blocked):
        adapter.place_forever_order(request, authorize=_block)
    assert fake_client.calls_for("POST", "/forever/orders") == []


def test_exit_all_blocked_before_wire(fake_client):
    fake_client.set_response("POST", "/exitall", {"data": {"success": True}})
    adapter = ExitAllAdapter(fake_client)
    with pytest.raises(_Blocked):
        adapter.exit_all(authorize=_block)
    assert fake_client.calls_for("POST", "/exitall") == []


def test_exit_all_reaches_wire_when_authorized(fake_client):
    fake_client.set_response("POST", "/exitall", {"data": {"success": True}})
    adapter = ExitAllAdapter(fake_client)
    adapter.exit_all(authorize=lambda: None)
    assert len(fake_client.calls_for("POST", "/exitall")) == 1
