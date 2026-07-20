"""Integration tests: OMS state transitions must match across execution modes."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.execution.gateway_submit import make_gateway_submit_fn
from application.execution.oms_backtest_adapter import create_execution_adapter
from application.oms.order_manager import OmsOrderCommand
from domain import OrderStatus, Side
from domain.entities import OrderResponse
from tests.conftest import build_test_trading_context


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
    adapter = create_execution_adapter("paper", trading_context)
    cmd = _command("test:parity:paper")
    result = adapter.place_order(cmd)

    assert result.success
    assert result.order is not None
    assert result.order.status == OrderStatus.OPEN
    stored = trading_context.order_manager.get_order(result.order.order_id)
    assert stored is not None
    assert stored.correlation_id == cmd.correlation_id


def test_replay_mode_records_order_in_oms(trading_context) -> None:
    adapter = create_execution_adapter("replay", trading_context)
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

    cmd = _command("test:parity:live")
    submit_fn = make_gateway_submit_fn(gateway)
    result = trading_context.order_manager.place_order(cmd, submit_fn=submit_fn)

    assert result.success
    assert result.order is not None
    assert result.order.order_id == "LIVE-001"
    gateway.place_order.assert_called_once()
    stored = trading_context.order_manager.get_order(result.order.order_id)
    assert stored is not None


def test_all_modes_publish_same_initial_order_status(trading_context) -> None:
    """Each mode must leave the order OPEN in OMS after placement."""
    from runtime.execution_target import build_execution_engine

    gateway = MagicMock()
    gateway.place_order.return_value = OrderResponse.ok(order_id="LIVE-002")

    paper_adapter = create_execution_adapter("paper", trading_context)
    replay_adapter = create_execution_adapter("replay", trading_context)
    live_engine = build_execution_engine(trading_context, "live", gateway=gateway)

    cases = [
        ("paper", paper_adapter, None),
        ("replay", replay_adapter, None),
        ("live", None, live_engine),
    ]
    statuses: list[OrderStatus] = []
    for mode, adapter, engine in cases:
        cmd = _command(f"test:parity:status:{mode}")
        result = adapter.place_order(cmd) if adapter is not None else engine.place_order(cmd)
        assert result.success, mode
        statuses.append(result.order.status)

    assert statuses == [OrderStatus.OPEN, OrderStatus.OPEN, OrderStatus.OPEN]


@pytest.fixture
def trading_context():
    return build_test_trading_context(replay_events=False)
