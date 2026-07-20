"""Fake implementations for OMS testing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from application.oms.order_manager import OmsOrderCommand, OrderResult
from application.oms.protocols import IReconciliationService
from domain import Order, OrderStatus
from domain.entities import Trade
from domain.reconciliation import DriftItem, ReconciliationReport
from infrastructure.event_bus import DomainEvent


@dataclass
class FakeRiskManager:
    """Fake risk manager with configurable behavior."""

    allow_all: bool = True
    kill_switch_active: bool = False
    kill_switch_set_calls: list[bool] = field(default_factory=list)

    def set_kill_switch(self, enabled: bool) -> None:
        self.kill_switch_active = enabled
        self.kill_switch_set_calls.append(enabled)

    def check_order(self, order: Order) -> Any:
        from types import SimpleNamespace

        if not self.allow_all:
            return SimpleNamespace(allowed=False, reason="FakeRiskManager: risk check failed")
        if self.kill_switch_active:
            return SimpleNamespace(allowed=False, reason="Kill switch active")
        return SimpleNamespace(allowed=True)


@dataclass
class FakePositionManager:
    """Fake position manager that tracks trade applications."""

    trades_applied: list[DomainEvent] = field(default_factory=list)

    def on_trade_applied(self, event: DomainEvent) -> None:
        self.trades_applied.append(event)

    def get_positions(self) -> list[dict[str, Any]]:
        return []

    def get_position(self, symbol: str, exchange: str = "NSE") -> None:
        """Return None (no position) for risk check compatibility."""
        return None


@dataclass
class FakeOrderManager:
    """Fake order manager that tracks order operations."""

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
        if self.fail_on_place:
            return OrderResult(success=False, error=self.fail_message)

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
        self.orders_cancelled.append(order_id)
        order = next((o for o in self.orders_placed if o.order_id == order_id), None)
        if order:
            return OrderResult(success=True, order=order.with_status(OrderStatus.CANCELLED))
        return OrderResult(success=False, error=f"Order {order_id} not found")

    def record_trade(self, trade: Trade) -> bool:
        self.trades_recorded.append(trade)
        return True


@dataclass
class FakeReconciliationService(IReconciliationService):
    """Fake reconciliation service with configurable drift behavior."""

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
        self.reconcile_calls += 1
        self.last_local_orders = local_orders
        self.last_local_positions = local_positions
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
class FakeExecutionAdapter:
    """Fake execution adapter for paper/replay mode testing."""

    auto_fill: bool = False
    fill_delay: float = 0.0
    orders_received: list[OmsOrderCommand] = field(default_factory=list)
    fail_on_place: bool = False

    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        self.orders_received.append(command)
        if self.fail_on_place:
            return OrderResult(success=False, error="FakeExecutionAdapter: execution failed")
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
class FakeBrokerGateway:
    """Fake broker gateway for testing order operations."""

    cancelled_orders: list[str] = field(default_factory=list)
    placed_orders: list[Order] = field(default_factory=list)
    fail_on_cancel: bool = False
    fail_on_place: bool = False

    def cancel_order(self, order_id: str) -> OrderResult:
        self.cancelled_orders.append(order_id)
        if self.fail_on_cancel:
            return OrderResult(success=False, error="FakeBrokerGateway: cancel failed")
        return OrderResult(success=True)

    def place_order(self, command: OmsOrderCommand) -> Order:
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
        from types import SimpleNamespace

        return SimpleNamespace(ltp=Decimal("100.00"))

    def positions(self) -> list:
        return []

    def funds(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(available_balance=Decimal("1000000.00"))
