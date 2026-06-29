"""Protocol-compliant fake implementations for testing.

These fakes replace monkeypatch/mock usage with real, observable test doubles
that implement the Protocol interfaces from application.oms.protocols.

Fakes are:
- Simple and deterministic
- Observable (record method calls for assertions)
- Protocol-compliant (pass mypy checks)
- Thread-safe where needed

Usage:
    from tests.fakes import FakeOrderManager, FakeRiskManager
    
    # Instead of:
    # monkeypatch.setattr(order_manager, '_risk_check', lambda: True)
    
    # Use:
    fake_risk = FakeRiskManager(allow_all=True)
    order_manager = OrderManager(risk_manager=fake_risk)
"""

from tests.fakes.fake_oms import (
    FakeBrokerGateway,
    FakeExecutionAdapter,
    FakeOrderManager,
    FakePositionManager,
    FakeReconciliationService,
    FakeRiskManager,
)
from tests.fakes.fake_trading import (
    FakeTradingOrchestrator,
)

__all__ = [
    "FakeBrokerGateway",
    "FakeExecutionAdapter",
    "FakeOrderManager",
    "FakePositionManager",
    "FakeReconciliationService",
    "FakeRiskManager",
    "FakeTradingOrchestrator",
]
