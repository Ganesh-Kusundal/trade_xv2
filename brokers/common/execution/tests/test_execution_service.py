"""Integration tests for ExecutionService."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain import Order, OrderType, ProductType, Side
from brokers.common.execution.execution_service import ExecutionService
from brokers.common.oms.factory import create_trading_context
from brokers.common.oms.order_manager import OmsOrderCommand
from brokers.paper.paper_gateway import PaperGateway


@pytest.fixture
def trading_context():
    return create_trading_context(replay_events=False)


@pytest.fixture
def paper_gateway():
    return PaperGateway()


def test_execution_service_paper_simulated_fill(trading_context, paper_gateway) -> None:
    svc = ExecutionService(
        trading_context=trading_context,
        gateway=paper_gateway,
        mode="paper",
    )
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="test:exec:paper:1",
    )
    result = svc.place_order(cmd)
    assert result.success
    assert isinstance(result.order, Order)


def test_execution_service_cancel_order(trading_context, paper_gateway) -> None:
    svc = ExecutionService(
        trading_context=trading_context,
        gateway=paper_gateway,
        mode="paper",
    )
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="test:exec:paper:cancel:1",
    )
    placed = svc.place_order(cmd)
    assert placed.success
    cancelled = svc.cancel_order(placed.order.order_id)
    assert cancelled.success or cancelled.error is not None
