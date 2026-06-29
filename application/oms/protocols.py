"""Protocol interfaces for OMS collaborators — eliminates `Any` type debt.

These Protocols use structural typing (duck typing at type-check time) to
define the interfaces expected by TradingContext, TradingOrchestrator, and
ExecutionService without requiring explicit inheritance.

Created as part of Task 6.1: Type the ServiceContainer & Eliminate `Any` Types.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Protocol, runtime_checkable

# Import OMS types needed for Protocol signatures
from application.oms.order_manager import OmsOrderCommand, OrderResult
from domain import Order
from domain.entities import Trade
from domain.reconciliation import ReconciliationReport
from infrastructure.event_bus import DomainEvent


@runtime_checkable
class IReconciliationService(Protocol):
    """Protocol for broker-specific reconciliation adapters.

    Implementations exist in brokers/dhan/reconciliation.py and
    brokers/upstox/reconciliation/service.py. The adapter must expose
    a reconcile() method that compares local OMS state with broker state.
    """

    def reconcile(
        self,
        local_orders: list | None = ...,
        local_positions: list | None = ...,
    ) -> ReconciliationReport:
        """Run reconciliation and return a drift report.

        Args:
            local_orders: Optional list of local OMS orders to compare against broker.
            local_positions: Optional list of local positions to compare against broker.

        Returns:
            ReconciliationReport with drift items, order/position counts, and repair stats.
        """
        ...


@runtime_checkable
class ICapitalAllocationFn(Protocol):
    """Protocol for capital allocation functions.

    A callable that returns the available capital as a Decimal. Used by
    RiskManager to enforce position size limits and exposure caps.
    """

    def __call__(self) -> Decimal:
        """Return available capital in INR.

        Returns:
            Decimal representing available capital.
        """
        ...


@runtime_checkable
class IOrderManager(Protocol):
    """Protocol for order management operations.

    Defines the interface expected by execution adapters and reconciliation
    services. Implementations must support order placement, cancellation,
    and trade recording.
    """

    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = ...,
    ) -> OrderResult:
        """Place an order through the OMS.

        Args:
            command: Order specification (symbol, side, quantity, etc.).
            submit_fn: Optional callable that submits to broker and returns Order.

        Returns:
            OrderResult with success/failure status and order details.
        """
        ...

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order by ID.

        Args:
            order_id: The order identifier to cancel.

        Returns:
            OrderResult with cancellation status.
        """
        ...

    def record_trade(self, trade: Trade) -> bool:
        """Record a trade/execution against an order.

        Args:
            trade: Trade object with execution details.

        Returns:
            True if trade was accepted, False if rejected (duplicate, etc.).
        """
        ...


@runtime_checkable
class IPositionManager(Protocol):
    """Protocol for position management operations.

    Used by reconciliation services and risk managers to query and update
    positions based on trade executions.
    """

    def on_trade_applied(self, event: DomainEvent) -> None:
        """Update positions based on a TRADE_APPLIED event.

        Args:
            event: DomainEvent with trade execution details.
        """
        ...


@runtime_checkable
class IRiskManager(Protocol):
    """Protocol for risk management operations.

    Provides kill switch and risk limit enforcement for the OMS.
    """

    def set_kill_switch(self, enabled: bool) -> None:
        """Enable or disable the risk kill switch.

        When enabled, all new order placements are rejected.

        Args:
            enabled: True to halt trading, False to resume.
        """
        ...


@runtime_checkable
class ITradingOrchestrator(Protocol):
    """Protocol for the trading orchestrator.

    Used by TradingContext for lifecycle management. The orchestrator
    connects Scanner→Strategy→OMS execution path.
    """

    @property
    def name(self) -> str:
        """Service name for lifecycle management."""
        ...

    def start(self) -> None:
        """Start the orchestrator (register event handlers, etc.)."""
        ...

    def stop(self, timeout_seconds: float = ...) -> None:
        """Stop the orchestrator and clean up resources.

        Args:
            timeout_seconds: Maximum time to wait for graceful shutdown.
        """
        ...


@runtime_checkable
class IExecutionAdapter(Protocol):
    """Protocol for execution mode adapters (paper/replay modes).

    Adapters handle simulated fills for non-live trading modes. Live mode
    bypasses the adapter entirely.
    """

    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = ...,
    ) -> OrderResult:
        """Place an order through the execution adapter.

        Args:
            command: Order specification.
            submit_fn: Optional submit function (used for live mode passthrough).

        Returns:
            OrderResult with execution status.
        """
        ...


@runtime_checkable
class IBrokerGateway(Protocol):
    """Protocol for broker gateway operations used in shutdown/cancellation.

    Provides the minimal interface needed by TradingContext.shutdown() to
    cancel orders at the broker level.
    """

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order at the broker.

        Args:
            order_id: The broker order ID to cancel.

        Returns:
            OrderResult with cancellation status.
        """
        ...


__all__ = [
    "IBrokerGateway",
    "ICapitalAllocationFn",
    "IExecutionAdapter",
    "IOrderManager",
    "IPositionManager",
    "IReconciliationService",
    "IRiskManager",
    "ITradingOrchestrator",
]
