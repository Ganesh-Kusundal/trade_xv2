"""Unit tests for ExecutionModeAdapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain import Side
from application.execution.execution_mode_adapter import (
    PaperOMSAdapter,
    ReplayOMSAdapter,
    create_execution_adapter,
)
from application.oms.factory import create_trading_context
from application.oms.order_manager import OmsOrderCommand


@pytest.fixture
def trading_context():
    return create_trading_context(replay_events=False)


def test_create_execution_adapter_modes(trading_context) -> None:
    assert isinstance(create_execution_adapter("paper", trading_context), PaperOMSAdapter)
    assert isinstance(create_execution_adapter("replay", trading_context), ReplayOMSAdapter)
    assert isinstance(create_execution_adapter("backtest", trading_context), ReplayOMSAdapter)


def test_create_execution_adapter_live_raises(trading_context) -> None:
    """Live mode is inlined in ExecutionService; the factory no longer handles it."""
    with pytest.raises(ValueError, match="live"):
        create_execution_adapter("live", trading_context)


def test_paper_adapter_places_simulated_order(trading_context) -> None:
    adapter = PaperOMSAdapter(trading_context)
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
