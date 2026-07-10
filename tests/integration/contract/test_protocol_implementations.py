"""Contract tests for Protocol implementations.

Verifies that concrete classes correctly implement the Protocol interfaces from Phase 6:
- IReconciliationService (DhanReconciliationService)
- IOrderManager (OrderManager)
- IPositionManager (PositionManager)
- IRiskManager (RiskManager)

Tests use isinstance() with @runtime_checkable protocols and verify method signatures.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

from application.oms._internal.risk_manager import RiskManager, RiskResult
from application.oms.order_manager import OmsOrderCommand, OrderManager
from application.oms.position_manager import PositionManager
from application.oms.protocols import (
    IOrderManager,
    IPositionManager,
    IReconciliationService,
    IRiskManager,
)
from brokers.dhan.portfolio.reconciliation import DhanReconciliationService
from domain.reconciliation import ReconciliationReport


class TestProtocolImplementations:
    """Verify concrete classes implement Protocol interfaces correctly."""

    def test_dhan_reconciliation_implements_protocol(self) -> None:
        """Verify DhanReconciliationService satisfies IReconciliationService protocol."""
        # Create minimal instance with None adapters (protocol check doesn't call methods)
        service = DhanReconciliationService(
            orders=None,  # type: ignore[arg-type]
            portfolio=None,  # type: ignore[arg-type]
            oms=None,
            auto_repair=False,
        )

        # Verify isinstance check passes
        assert isinstance(service, IReconciliationService), (
            "DhanReconciliationService must satisfy IReconciliationService protocol"
        )

        # Verify method signature matches protocol
        sig = inspect.signature(service.reconcile)
        params = list(sig.parameters.keys())
        assert "local_orders" in params, (
            f"reconcile() must have 'local_orders' parameter, got {params}"
        )
        assert "local_positions" in params, (
            f"reconcile() must have 'local_positions' parameter, got {params}"
        )

        # Verify return type annotation
        return_annotation = sig.return_annotation
        assert return_annotation == ReconciliationReport or "ReconciliationReport" in str(
            return_annotation
        ), f"reconcile() must return ReconciliationReport, got {return_annotation}"

    def test_order_manager_implements_protocol(self) -> None:
        """Verify OrderManager satisfies IOrderManager protocol."""
        # Create minimal instance
        manager = OrderManager()

        # Verify isinstance check passes
        assert isinstance(manager, IOrderManager), (
            "OrderManager must satisfy IOrderManager protocol"
        )

        # Verify place_order signature
        sig = inspect.signature(manager.place_order)
        params = list(sig.parameters.keys())
        assert "request" in params or "command" in params, (
            f"place_order() must have 'request' or 'command' parameter, got {params}"
        )
        assert "submit_fn" in params, (
            f"place_order() must have 'submit_fn' parameter, got {params}"
        )

        # Verify cancel_order signature
        sig_cancel = inspect.signature(manager.cancel_order)
        params_cancel = list(sig_cancel.parameters.keys())
        assert "order_id" in params_cancel, (
            f"cancel_order() must have 'order_id' parameter, got {params_cancel}"
        )

        # Verify record_trade signature
        sig_trade = inspect.signature(manager.record_trade)
        params_trade = list(sig_trade.parameters.keys())
        assert "trade" in params_trade, (
            f"record_trade() must have 'trade' parameter, got {params_trade}"
        )

    def test_position_manager_implements_protocol(self) -> None:
        """Verify PositionManager satisfies IPositionManager protocol."""
        # Create minimal instance
        manager = PositionManager()

        # Verify isinstance check passes
        assert isinstance(manager, IPositionManager), (
            "PositionManager must satisfy IPositionManager protocol"
        )

        # Verify on_trade_applied signature
        sig = inspect.signature(manager.on_trade_applied)
        params = list(sig.parameters.keys())
        assert "event" in params, (
            f"on_trade_applied() must have 'event' parameter, got {params}"
        )

        # Verify return type is None
        return_annotation = sig.return_annotation
        assert return_annotation is None or return_annotation == type(None) or "None" in str(
            return_annotation
        ), f"on_trade_applied() must return None, got {return_annotation}"

    def test_risk_manager_implements_protocol(self) -> None:
        """Verify RiskManager satisfies IRiskManager protocol."""
        # Create minimal instance with required dependencies
        from application.oms._internal.risk_manager import RiskConfig

        position_manager = PositionManager()
        config = RiskConfig()

        manager = RiskManager(
            position_manager=position_manager,
            config=config,
        )

        # Verify isinstance check passes
        assert isinstance(manager, IRiskManager), (
            "RiskManager must satisfy IRiskManager protocol"
        )

        # Verify set_kill_switch signature
        sig = inspect.signature(manager.set_kill_switch)
        params = list(sig.parameters.keys())
        assert "active" in params or "enabled" in params, (
            f"set_kill_switch() must have 'active' or 'enabled' parameter, got {params}"
        )

        # Verify return type is None
        return_annotation = sig.return_annotation
        assert return_annotation is None or return_annotation == type(None) or "None" in str(
            return_annotation
        ), f"set_kill_switch() must return None, got {return_annotation}"

    def test_protocol_runtime_checkable_rejects_wrong_type(self) -> None:
        """Verify non-implementing class fails isinstance check."""
        # Create a class that does NOT implement the protocol
        class NotAReconciliationService:
            def some_other_method(self) -> None:
                pass

        service = NotAReconciliationService()

        # Verify isinstance check fails
        assert not isinstance(service, IReconciliationService), (
            "NotAReconciliationService must NOT satisfy IReconciliationService protocol"
        )

        # Verify another non-implementing class
        class NotAnOrderManager:
            def place_order(self) -> None:
                pass

        manager = NotAnOrderManager()
        assert not isinstance(manager, IOrderManager), (
            "NotAnOrderManager must NOT satisfy IOrderManager protocol"
        )

    def test_reconciliation_report_matches_protocol(self) -> None:
        """Verify ReconciliationReport has required fields from protocol."""
        report = ReconciliationReport(timestamp_ms=1234567890)

        # Verify required fields exist
        assert hasattr(report, "drift_items"), "ReconciliationReport must have drift_items"
        assert hasattr(report, "broker_orders"), "ReconciliationReport must have broker_orders"
        assert hasattr(report, "broker_positions"), "ReconciliationReport must have broker_positions"
        assert hasattr(report, "orders_repaired"), "ReconciliationReport must have orders_repaired"
        assert hasattr(report, "positions_repaired"), "ReconciliationReport must have positions_repaired"
        assert hasattr(report, "timestamp_ms"), "ReconciliationReport must have timestamp_ms"

        # Verify types
        assert isinstance(report.drift_items, list), "drift_items must be a list"
        assert isinstance(report.broker_orders, int), "broker_orders must be an int"
        assert isinstance(report.broker_positions, int), "broker_positions must be an int"
        assert isinstance(report.timestamp_ms, int), "timestamp_ms must be an int"

    def test_order_command_matches_protocol(self) -> None:
        """Verify OmsOrderCommand has required fields for protocol usage."""
        from domain.types import Side

        command = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500.00"),
            correlation_id="test:corr123",
        )

        # Verify required fields exist
        assert hasattr(command, "symbol"), "OmsOrderCommand must have symbol"
        assert hasattr(command, "exchange"), "OmsOrderCommand must have exchange"
        assert hasattr(command, "side"), "OmsOrderCommand must have side"
        assert hasattr(command, "quantity"), "OmsOrderCommand must have quantity"
        assert hasattr(command, "price"), "OmsOrderCommand must have price"
        assert hasattr(command, "correlation_id"), "OmsOrderCommand must have correlation_id"

        # Verify types
        assert isinstance(command.symbol, str), "symbol must be a str"
        assert isinstance(command.exchange, str), "exchange must be a str"
        assert isinstance(command.quantity, int), "quantity must be an int"
        assert isinstance(command.price, Decimal), "price must be a Decimal"

    def test_risk_result_matches_protocol(self) -> None:
        """Verify RiskResult has allowed + reason fields."""
        # Test allowed=True case
        result_allowed = RiskResult(allowed=True)
        assert hasattr(result_allowed, "allowed"), "RiskResult must have allowed field"
        assert hasattr(result_allowed, "reason"), "RiskResult must have reason field"
        assert result_allowed.allowed is True, "allowed should be True"
        assert result_allowed.reason is None, "reason should be None when allowed"

        # Test allowed=False case
        result_rejected = RiskResult(allowed=False, reason="Kill switch active")
        assert result_rejected.allowed is False, "allowed should be False"
        assert result_rejected.reason == "Kill switch active", (
            f"reason should match, got {result_rejected.reason}"
        )

        # Verify types
        assert isinstance(result_allowed.allowed, bool), "allowed must be a bool"
        assert isinstance(result_rejected.reason, str), "reason must be a str when provided"
