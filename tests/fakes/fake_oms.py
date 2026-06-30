"""Fake implementations for OMS Protocol interfaces.

These fakes implement the Protocol interfaces from application.oms.protocols
and provide observable, deterministic behavior for testing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from application.oms.order_manager import OmsOrderCommand, OrderResult
from application.oms.protocols import (
    IBrokerGateway,
    IExecutionAdapter,
    IOrderManager,
    IPositionManager,
    IReconciliationService,
    IRiskManager,
)
from domain import Order, OrderStatus
from domain.entities import Trade
from domain.reconciliation import DriftItem, ReconciliationReport
from infrastructure.event_bus import DomainEvent


@dataclass
class FakeRiskManager(IRiskManager):
    """Fake risk manager with configurable behavior.

    Instead of monkeypatching risk checks, inject this fake:

        # BEFORE:
        monkeypatch.setattr(order_manager, '_risk_manager', MagicMock())

        # AFTER:
        fake_risk = FakeRiskManager(allow_all=True)
        order_manager = OrderManager(risk_manager=fake_risk)
    """

    allow_all: bool = True
    kill_switch_active: bool = False
    kill_switch_set_calls: list[bool] = field(default_factory=list)

    def set_kill_switch(self, enabled: bool) -> None:
        """Record kill switch state changes."""
        self.kill_switch_active = enabled
        self.kill_switch_set_calls.append(enabled)

    def check_order(self, order: Order) -> Any:
        """Simulate risk check result.

        Returns a mock RiskResult with .allowed attribute.
        """
        from types import SimpleNamespace

        if not self.allow_all:
            return SimpleNamespace(allowed=False, reason="FakeRiskManager: risk check failed")

        if self.kill_switch_active:
            return SimpleNamespace(allowed=False, reason="Kill switch active")

        return SimpleNamespace(allowed=True)


@dataclass
class FakePositionManager(IPositionManager):
    """Fake position manager that tracks trade applications.

    Instead of mocking position updates, use this observable fake:

        # BEFORE:
        monkeypatch.setattr(position_manager, 'on_trade_applied', MagicMock())

        # AFTER:
        fake_positions = FakePositionManager()
        # ... use in test ...
        assert len(fake_positions.trades_applied) == 1
    """

    trades_applied: list[DomainEvent] = field(default_factory=list)

    def on_trade_applied(self, event: DomainEvent) -> None:
        """Record trade application event."""
        self.trades_applied.append(event)

    def get_positions(self) -> list[dict[str, Any]]:
        """Return synthetic positions for testing."""
        return []


@dataclass
class FakeOrderManager(IOrderManager):
    """Fake order manager that tracks order operations.

    Provides a simple, deterministic order management implementation
    for testing without real broker dependencies.

        # BEFORE:
        mock_om = MagicMock()
        mock_om.place_order.return_value = OrderResult(success=True)

        # AFTER:
        fake_om = FakeOrderManager()
        result = fake_om.place_order(command)
        assert len(fake_om.orders_placed) == 1
    """

    orders_placed: list[Order] = field(default_factory=list)
    orders_cancelled: list[str] = field(default_factory=list)
    trades_recorded: list[Trade] = field(default_factory=list)
    fail_on_place: bool = False
    fail_message: str = "FakeOrderManager: intentional failure"

    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Place a fake order and record it."""
        if self.fail_on_place:
            return OrderResult(success=False, error=self.fail_message)

        # Create a synthetic order
        order = Order(
            order_id=f"FAKE-ORD-{len(self.orders_placed) + 1:04d}",
            symbol=command.symbol,
            exchange=command.exchange,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            product_type=command.product_type,
            status=OrderStatus.OPEN,
            correlation_id=command.correlation_id,
        )

        self.orders_placed.append(order)
        return OrderResult(success=True, order=order)

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel a fake order and record it."""
        self.orders_cancelled.append(order_id)

        # Find the order if it exists
        order = next(
            (o for o in self.orders_placed if o.order_id == order_id),
            None,
        )

        if order:
            cancelled_order = order.with_status(OrderStatus.CANCELLED)
            return OrderResult(success=True, order=cancelled_order)

        return OrderResult(success=False, error=f"Order {order_id} not found")

    def record_trade(self, trade: Trade) -> bool:
        """Record a trade execution."""
        self.trades_recorded.append(trade)
        return True


@dataclass
class FakeReconciliationService(IReconciliationService):
    """Fake reconciliation service with configurable drift behavior.

    Instead of using MagicMock for reconciliation:

        # BEFORE:
        mock_recon = MagicMock()
        mock_recon.reconcile.return_value = MagicMock(has_drift=False)

        # AFTER:
        fake_recon = FakeReconciliationService(has_drift=False)
        report = fake_recon.reconcile()
        assert not report.has_drift
    """

    has_drift: bool = False
    drift_count: int = 0
    reconcile_calls: int = 0
    last_local_orders: list | None = None
    last_local_positions: list | None = None

    def reconcile(
        self,
        local_orders: list | None = None,
        local_positions: list | None = None,
    ) -> ReconciliationReport:
        """Run fake reconciliation and return a real ReconciliationReport."""
        self.reconcile_calls += 1
        self.last_local_orders = local_orders
        self.last_local_positions = local_positions

        # Create real ReconciliationReport with drift items
        drift_items = []
        if self.has_drift:
            for i in range(self.drift_count):
                drift_items.append(
                    DriftItem(
                        kind="ORDER_MISMATCH",
                        severity="HIGH",
                        symbol=f"SYM{i}",
                        details=f"Drift item {i}",
                    )
                )

        return ReconciliationReport(
            drift_items=drift_items,
            broker_orders=0,
            broker_positions=0,
            orders_repaired=0,
            positions_repaired=0,
        )


@dataclass
class FakeExecutionAdapter(IExecutionAdapter):
    """Fake execution adapter for paper/replay mode testing.

    Simulates order execution with configurable fill behavior.

        # BEFORE:
        monkeypatch.setattr(adapter, 'place_order', MagicMock())

        # AFTER:
        fake_adapter = FakeExecutionAdapter(auto_fill=True)
        result = fake_adapter.place_order(command)
        assert result.order.status == OrderStatus.FILLED
    """

    auto_fill: bool = False
    fill_delay: float = 0.0
    orders_received: list[OmsOrderCommand] = field(default_factory=list)
    fail_on_place: bool = False

    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Process order through fake execution adapter."""
        self.orders_received.append(command)

        if self.fail_on_place:
            return OrderResult(success=False, error="FakeExecutionAdapter: execution failed")

        # Create filled order if auto_fill is enabled
        status = OrderStatus.FILLED if self.auto_fill else OrderStatus.OPEN
        filled_quantity = command.quantity if self.auto_fill else 0

        order = Order(
            order_id=f"FAKE-EXEC-{len(self.orders_received):04d}",
            symbol=command.symbol,
            exchange=command.exchange,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            product_type=command.product_type,
            status=status,
            filled_quantity=filled_quantity,
            correlation_id=command.correlation_id,
        )

        return OrderResult(success=True, order=order)


@dataclass
class FakeBrokerGateway(IBrokerGateway):
    """Fake broker gateway for testing order operations.

    Simulates broker interactions without real network calls.

        # BEFORE:
        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = OrderResult(success=True)

        # AFTER:
        fake_gateway = FakeBrokerGateway()
        result = fake_gateway.cancel_order("ORD-001")
        assert result.success
        assert "ORD-001" in fake_gateway.cancelled_orders
    """

    cancelled_orders: list[str] = field(default_factory=list)
    placed_orders: list[Order] = field(default_factory=list)
    fail_on_cancel: bool = False
    fail_on_place: bool = False

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel order at fake broker."""
        self.cancelled_orders.append(order_id)

        if self.fail_on_cancel:
            return OrderResult(success=False, error="FakeBrokerGateway: cancel failed")

        return OrderResult(success=True)

    def place_order(self, command: OmsOrderCommand) -> Order:
        """Place order at fake broker."""
        if self.fail_on_place:
            raise RuntimeError("FakeBrokerGateway: place_order failed")

        order = Order(
            order_id=f"BROKER-ORD-{len(self.placed_orders) + 1:04d}",
            symbol=command.symbol,
            exchange=command.exchange,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            product_type=command.product_type,
            status=OrderStatus.OPEN,
            correlation_id=command.correlation_id,
        )

        self.placed_orders.append(order)
        return order

    def quote(self, symbol: str, exchange: str) -> Any:
        """Return fake quote."""
        from types import SimpleNamespace
        return SimpleNamespace(ltp=Decimal("100.00"))

    def positions(self) -> list:
        """Return fake positions."""
        return []

    def funds(self) -> Any:
        """Return fake funds."""
        from types import SimpleNamespace
        return SimpleNamespace(available_balance=Decimal("1000000.00"))
