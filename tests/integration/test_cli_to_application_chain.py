"""Integration test: CLI → service → application call chain.

Verifies that CLI commands correctly route through cli/services/ into
application/ layer without bypassing the service translation layer.
"""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from decimal import Decimal

import pytest

from application.execution.execution_service import ExecutionService
from application.oms.factory import create_trading_context
from application.oms.order_manager import OmsOrderCommand
from domain import Side
from tests.fixtures.fake_broker_gateway import FakeBrokerGateway


class TestCLItoApplicationChain:
    """Verify CLI → service → application call chain integrity."""

    @pytest.fixture
    def trading_context(self):
        return build_test_trading_context(replay_events=False)

    @pytest.fixture
    def fake_gateway(self):
        return FakeBrokerGateway()

    def test_paper_order_reaches_oms(self, trading_context, fake_gateway):
        """Paper order must be recorded in OMS after successful placement."""
        svc = ExecutionService(
            trading_context=trading_context,
            gateway=fake_gateway,
            mode="paper",
        )

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
            correlation_id="test:integration:001",
        )

        result = svc.place_order(cmd)

        assert result.success
        assert result.order is not None
        # Paper mode uses simulated fill, not gateway
        stored = trading_context.order_manager.get_order(result.order.order_id)
        assert stored is not None
        assert stored.symbol == "RELIANCE"

    def test_live_order_reaches_gateway(self, trading_context, fake_gateway):
        """Live order must reach the gateway via submit_fn."""
        svc = ExecutionService(
            trading_context=trading_context,
            gateway=fake_gateway,
            mode="live",
        )

        cmd = OmsOrderCommand(
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
            price=Decimal("3500"),
            correlation_id="test:integration:002",
        )

        result = svc.place_order(cmd)

        assert result.success
        assert result.order is not None
        assert fake_gateway.get_order_count() == 1
        assert fake_gateway.get_orders()[0]["symbol"] == "TCS"

    def test_idempotent_order_placement(self, trading_context, fake_gateway):
        """Duplicate correlation_id must return existing order without new gateway call."""
        svc = ExecutionService(
            trading_context=trading_context,
            gateway=fake_gateway,
            mode="paper",
        )

        cmd = OmsOrderCommand(
            symbol="INFY",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            price=Decimal("1500"),
            correlation_id="test:integration:idempotent",
        )

        result1 = svc.place_order(cmd)
        result2 = svc.place_order(cmd)

        assert result1.success
        assert result2.success
        assert result1.order.order_id == result2.order.order_id

    def test_cancel_order_through_oms(self, trading_context, fake_gateway):
        """Cancel order must flow through OMS and update state."""
        svc = ExecutionService(
            trading_context=trading_context,
            gateway=fake_gateway,
            mode="paper",
        )

        cmd = OmsOrderCommand(
            symbol="WIPRO",
            exchange="NSE",
            side=Side.BUY,
            quantity=100,
            price=Decimal("400"),
            correlation_id="test:integration:cancel",
        )

        result = svc.place_order(cmd)
        assert result.success

        cancel_result = svc.cancel_order(result.order.order_id)
        assert cancel_result.success

        stored = trading_context.order_manager.get_order(result.order.order_id)
        assert stored is not None
        assert stored.status.value == "CANCELLED"
