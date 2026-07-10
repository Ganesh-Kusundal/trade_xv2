"""Integration tests for ExecutionService."""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from decimal import Decimal

import pytest

from application.execution.execution_service import ExecutionService
from application.oms.factory import create_trading_context
from application.oms.order_manager import OmsOrderCommand
from brokers.paper.paper_gateway import PaperGateway
from domain import Order, OrderType, ProductType, Side


@pytest.fixture
def trading_context():
    return build_test_trading_context(replay_events=False)


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


def test_execution_service_live_uses_place_order_use_case(
    trading_context, paper_gateway, monkeypatch
) -> None:
    """Live path must route through PlaceOrderUseCase (not bare OrderManager)."""
    from application.execution import place_order_use_case as pouc_mod

    calls: list[object] = []
    real_execute = pouc_mod.PlaceOrderUseCase.execute

    def tracking_execute(self, request):
        calls.append(request)
        return real_execute(self, request)

    monkeypatch.setattr(pouc_mod.PlaceOrderUseCase, "execute", tracking_execute)

    svc = ExecutionService(
        trading_context=trading_context,
        gateway=paper_gateway,
        mode="live",
    )
    cmd = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id="test:exec:live:usecase:1",
    )
    result = svc.place_order(cmd)
    assert result.success
    assert len(calls) == 1
    assert calls[0] is cmd
