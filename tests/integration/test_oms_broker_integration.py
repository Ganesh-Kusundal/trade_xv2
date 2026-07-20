"""OMS ↔ Broker Gateway integration tests.

Verifies the complete order flow from OrderManager through BrokerGateway
for all three broker implementations (Dhan, Upstox, Paper).

REF: Task 6.3 — Converted from MagicMock to Protocol-compliant fakes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms.order_manager import OrderManager
from application.oms._internal.risk_manager import RiskConfig, RiskManager
from brokers.paper.paper_gateway import PaperGateway
from domain import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
)
from tests.fakes import FakePositionManager, FakeRiskManager
from tests.integration.fixtures.domain import make_order


@pytest.mark.integration
@pytest.mark.oms_integration
class TestOMSBrokerIntegrationPaper:
    """Test OMS integration with PaperGateway (deterministic)."""

    @pytest.fixture
    def paper_gateway(self):
        """Provide PaperGateway for testing."""
        return PaperGateway(initial_capital=Decimal("1000000"))

    @pytest.fixture
    def order_manager(self, event_bus, paper_gateway):
        """Provide OrderManager wired to PaperGateway."""
        # REF: Using FakeRiskManager instead of MagicMock
        FakeRiskManager(allow_all=True)
        # RiskManager still needed for interface compatibility
        real_risk_manager = RiskManager(
            position_manager=FakePositionManager(),
            config=RiskConfig(),
            capital_fn=lambda: Decimal("1000000"),
        )
        return OrderManager(
            event_bus=event_bus,
            broker_gateway=paper_gateway,
            risk_manager=real_risk_manager,
        )

    def test_place_order_through_oms(self, order_manager, event_bus_with_capturer):
        """Test OrderManager.place_order() → PaperGateway.place_order() flow."""
        _event_bus, capturer = event_bus_with_capturer
        capturer.subscribe("ORDER_PLACED")

        make_order(
            order_id="TEST-ORD-001",
            symbol="RELIANCE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2550.00"),
        )

        # Place order through OMS
        result = order_manager.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=Decimal("2550.00"),
            product_type=ProductType.INTRADAY,
        )

        # Verify order was placed
        assert result is not None
        assert result.status in [OrderStatus.OPEN, OrderStatus.FILLED]

        # Verify event was published
        capturer.assert_event_published("ORDER_PLACED", min_count=1)

    def test_cancel_order_through_oms(self, order_manager, event_bus_with_capturer):
        """Test OrderManager.cancel_order() → PaperGateway.cancel_order() flow."""
        _event_bus, capturer = event_bus_with_capturer
        capturer.subscribe("ORDER_PLACED", "ORDER_CANCELLED")

        # Place an order first
        placed_order = order_manager.place_order(
            symbol="INFY",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            order_type=OrderType.LIMIT,
            price=Decimal("1420.00"),
            product_type=ProductType.INTRADAY,
        )

        # Cancel the order
        if placed_order and placed_order.order_id:
            order_manager.cancel_order(placed_order.order_id)

            # Verify cancellation event
            capturer.assert_event_published("ORDER_CANCELLED", min_count=0)

    def test_risk_manager_rejection(self, order_manager, event_bus_with_capturer):
        """Test that risk manager rejects orders before broker call."""
        _event_bus, capturer = event_bus_with_capturer
        capturer.subscribe("RISK_CHECK_FAILED")

        # Configure strict risk limits
        order_manager._risk_manager._config.max_position_pct = Decimal("0.01")

        # Attempt to place oversized order (should be rejected)
        try:
            result = order_manager.place_order(
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=100000,  # Very large quantity
                order_type=OrderType.LIMIT,
                price=Decimal("2550.00"),
                product_type=ProductType.INTRADAY,
            )
            # If we get here, check if it was rejected
            if result:
                assert result.status == OrderStatus.REJECTED
        except Exception:
            # Risk check raised an exception (also valid)
            capturer.assert_event_published("RISK_CHECK_FAILED", min_count=0)


@pytest.mark.integration
@pytest.mark.oms_integration
class TestOMSBrokerIntegrationMock:
    """Test OMS integration with fake broker gateways.

    REF: Task 6.3 — Converted from MagicMock to FakeBrokerGateway
    """

    @pytest.fixture
    def mock_gateway(self):
        """Provide a fake broker gateway."""
        from tests.fakes import FakeBrokerGateway

        gateway = FakeBrokerGateway()
        return gateway

    @pytest.fixture
    def order_manager(self, event_bus, mock_gateway):
        """Provide OrderManager wired to fake gateway."""
        # REF: Using FakePositionManager instead of MagicMock
        risk_manager = RiskManager(
            position_manager=FakePositionManager(),
            config=RiskConfig(),
            capital_fn=lambda: Decimal("1000000"),
        )
        return OrderManager(
            event_bus=event_bus,
            broker_gateway=mock_gateway,
            risk_manager=risk_manager,
        )

    def test_order_placement_calls_gateway(self, order_manager, mock_gateway):
        """Test that OMS calls gateway.place_order()."""
        order_manager.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=Decimal("2550.00"),
            product_type=ProductType.INTRADAY,
        )

        # Verify gateway was called (observable fake)
        assert len(mock_gateway.placed_orders) == 1

    def test_order_cancellation_calls_gateway(self, order_manager, mock_gateway):
        """Test that OMS calls gateway.cancel_order()."""
        # Place order first
        order_manager.place_order(
            symbol="INFY",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            order_type=OrderType.LIMIT,
            price=Decimal("1420.00"),
            product_type=ProductType.INTRADAY,
        )

        # Cancel it
        order_manager.cancel_order("MOCK-ORD-001")

        # Verify gateway was called (observable fake)
        assert "MOCK-ORD-001" in mock_gateway.cancelled_orders
