"""Unit tests for ExecutionModeAdapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.execution.execution_mode_adapter import (
    SimulatedOMSAdapter,
    create_execution_adapter,
)
from application.oms.factory import create_trading_context
from application.oms.order_manager import OmsOrderCommand
from domain import Side


@pytest.fixture
def trading_context():
    return create_trading_context(replay_events=False)


def test_create_execution_adapter_modes(trading_context) -> None:
    assert isinstance(create_execution_adapter("paper", trading_context), SimulatedOMSAdapter)
    assert isinstance(create_execution_adapter("replay", trading_context), SimulatedOMSAdapter)
    assert isinstance(create_execution_adapter("backtest", trading_context), SimulatedOMSAdapter)


def test_create_execution_adapter_live_raises(trading_context) -> None:
    with pytest.raises(ValueError, match="Unknown execution mode"):
        create_execution_adapter("live", trading_context)


def test_paper_adapter_places_simulated_order(trading_context) -> None:
    adapter = create_execution_adapter("paper", trading_context)
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:paper:1",
    )
    result = adapter.place_order(cmd)
    assert result.success
    assert result.order is not None
    assert result.order.order_id.startswith("paper-")


def test_replay_adapter_places_simulated_order(trading_context) -> None:
    adapter = create_execution_adapter("replay", trading_context)
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        correlation_id="test:replay:1",
    )
    result = adapter.place_order(cmd)
    assert result.success
    assert result.order is not None
    assert result.order.order_id.startswith("bt-")
