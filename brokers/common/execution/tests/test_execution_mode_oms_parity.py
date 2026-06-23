"""Integration tests: OMS state transitions must match across execution modes."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.core.domain import OrderStatus, Side
from brokers.common.core.models import OrderResponse
from brokers.common.execution.execution_mode_adapter import (
    LiveOMSAdapter,
    PaperOMSAdapter,
    ReplayOMSAdapter,
)
from brokers.common.execution.gateway_submit import make_gateway_submit_fn
from brokers.common.oms.factory import create_trading_context
from brokers.common.oms.order_manager import OmsOrderCommand


def _command(correlation_id: str) -> OmsOrderCommand:
    return OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id=correlation_id,
    )


def test_paper_mode_records_order_in_oms(trading_context) -> None:
    adapter = PaperOMSAdapter(trading_context)
    cmd = _command("test:parity:paper")
    result = adapter.place_order(cmd)

    assert result.success
    assert result.order is not None
    assert result.order.status == OrderStatus.OPEN
    stored = trading_context.order_manager.get_order(result.order.order_id)
    assert stored is not None
    assert stored.correlation_id == cmd.correlation_id


def test_replay_mode_records_order_in_oms(trading_context) -> None:
    adapter = ReplayOMSAdapter(trading_context)
    cmd = _command("test:parity:replay")
    result = adapter.place_order(cmd)

    assert result.success
    assert result.order is not None
    assert result.order.order_id.startswith("bt-")
    stored = trading_context.order_manager.get_order(result.order.order_id)
    assert stored is not None
    assert stored.correlation_id == cmd.correlation_id


def test_live_mode_uses_submit_fn_and_records_in_oms(trading_context) -> None:
    gateway = MagicMock()
    gateway.place_order.return_value = OrderResponse.ok(order_id="LIVE-001")

    adapter = LiveOMSAdapter(trading_context)
    cmd = _command("test:parity:live")
    submit_fn = make_gateway_submit_fn(gateway, transport_only=True)
    result = adapter.place_order(cmd, submit_fn=submit_fn)

    assert result.success
    assert result.order is not None
    assert result.order.order_id == "LIVE-001"
    gateway.place_order.assert_called_once()
    assert gateway.place_order.call_args.kwargs["transport_only"] is True
    stored = trading_context.order_manager.get_order(result.order.order_id)
    assert stored is not None


def test_all_modes_publish_same_initial_order_status(trading_context) -> None:
    """Each mode must leave the order OPEN in OMS after placement."""
    gateway = MagicMock()
    gateway.place_order.return_value = OrderResponse.ok(order_id="LIVE-002")

    cases = [
        ("paper", PaperOMSAdapter(trading_context), None),
        ("replay", ReplayOMSAdapter(trading_context), None),
        (
            "live",
            LiveOMSAdapter(trading_context),
            make_gateway_submit_fn(gateway, transport_only=True),
        ),
    ]
    statuses: list[OrderStatus] = []
    for mode, adapter, submit_fn in cases:
        cmd = _command(f"test:parity:status:{mode}")
        result = adapter.place_order(cmd, submit_fn=submit_fn)
        assert result.success, mode
        statuses.append(result.order.status)

    assert statuses == [OrderStatus.OPEN, OrderStatus.OPEN, OrderStatus.OPEN]


@pytest.fixture
def trading_context():
    return create_trading_context(replay_events=False)
