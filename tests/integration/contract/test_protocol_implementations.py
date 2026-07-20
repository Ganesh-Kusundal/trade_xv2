"""Contract tests for OMS Protocol implementations."""

from __future__ import annotations

import inspect

from application.oms.protocols import IReconciliationService
from brokers.dhan.portfolio.reconciliation import DhanReconciliationService
from domain.reconciliation import ReconciliationReport


class TestProtocolImplementations:
    """Verify concrete classes implement the remaining Protocol interfaces."""

    def test_dhan_reconciliation_implements_protocol(self) -> None:
        service = DhanReconciliationService(
            orders=None,  # type: ignore[arg-type]
            portfolio=None,  # type: ignore[arg-type]
            oms=None,
            auto_repair=False,
        )
        assert isinstance(service, IReconciliationService)
        sig = inspect.signature(service.reconcile)
        params = list(sig.parameters.keys())
        assert "local_orders" in params
        assert "local_positions" in params
        return_annotation = sig.return_annotation
        assert return_annotation == ReconciliationReport or "ReconciliationReport" in str(
            return_annotation
        )

    def test_order_manager_exposes_order_lifecycle_api(self) -> None:
        from application.oms.order_manager import OrderManager

        manager = OrderManager()
        assert callable(manager.place_order)
        assert callable(manager.cancel_order)

    def test_risk_manager_satisfies_risk_manager_port(self) -> None:
        from application.oms._internal.risk_manager import RiskConfig, RiskManager
        from application.oms.position_manager import PositionManager
        from infrastructure.event_bus.event_bus import EventBus, EventBusConfig

        event_bus = EventBus(config=EventBusConfig(fail_fast=False))
        position_manager = PositionManager(event_bus=event_bus)
        risk_manager = RiskManager(position_manager=position_manager, config=RiskConfig())
        assert callable(risk_manager.check_order)
        assert callable(risk_manager.is_kill_switch_active)
