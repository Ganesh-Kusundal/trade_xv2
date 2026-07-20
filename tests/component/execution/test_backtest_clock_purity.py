"""Backtest/replay orders use VirtualClock, not wall time."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from tests.conftest import build_test_trading_context

from application.execution.oms_backtest_adapter import create_oms_backtest_adapter
from domain import Side
from domain.ports.time_service import get_current_clock


@pytest.fixture
def trading_context():
    return build_test_trading_context(replay_events=False)


def test_oms_backtest_adapter_uses_bar_timestamp(trading_context) -> None:
    adapter = create_oms_backtest_adapter(trading_context, mode="replay")
    bar_ts = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc)

    order_id = adapter.open_long(
        symbol="RELIANCE",
        exchange="NSE",
        quantity=1,
        price=Decimal("2500"),
        timestamp=bar_ts,
    )

    assert order_id is not None
    assert adapter.get_orders()
    order = adapter.get_orders()[0]
    assert order.timestamp == bar_ts


def test_simulated_fill_uses_injected_clock(trading_context) -> None:
    from application.execution.simulated_fill import make_simulated_submit_fn
    from application.oms.order_manager import OmsOrderCommand
    from domain import OrderType, ProductType
    from domain.ports.time_service import use_clock
    from domain.ports.time_service_impls import VirtualClock

    fixed = datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc)
    cmd = OmsOrderCommand(
        symbol="TCS",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("4000"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="clock-test-1",
    )
    with use_clock(VirtualClock(initial=fixed)):
        order = make_simulated_submit_fn(cmd)(cmd)
        assert order.timestamp == fixed
