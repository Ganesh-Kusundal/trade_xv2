"""Orchestrator now converts signals via ExecutionPlan.

Guarantees: gating (kill-switch / min-confidence / ENG-003 refusal) is
preserved; EXECUTION_PLAN_BUILT + ORDER_REQUESTED are published; and
SIGNAL_EXECUTED still fires. RISK_* events are owned by OrderValidator.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from application.oms.order_manager import OrderResult
from application.trading.trading_orchestrator import OrchestratorConfig, TradingOrchestrator
from domain.events.types import (
    EventType,
    ExecutionPlanBuiltEvent,
    OrderRequestedEvent,
)
from domain.models.trading import SignalDTO
from domain.orders.execution_plan import ExecutionPlan


class _FakeOrder:
    def __init__(self, order_id: str, correlation_id: str) -> None:
        self.order_id = order_id
        self.correlation_id = correlation_id


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    def publish(self, event) -> None:
        self.events.append(event)

    def subscribe(self, *args, **kwargs):
        return "token"


def _signal(**kw) -> SignalDTO:
    base = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "signal_type": "BUY",
        "confidence": Decimal("0.9"),
        "quantity": 1,
        "entry_price": Decimal("100"),
        "strategy": "momentum",
    }
    base.update(kw)
    return SignalDTO(**base)


def _orch(bus: _Bus, kill_switch: bool = False, min_confidence: float = 0.7, order_fn=None):
    rm = MagicMock()
    rm.is_kill_switch_active.return_value = kill_switch
    om = MagicMock()
    om.risk_manager = rm
    engine = MagicMock()
    if order_fn is not None:
        engine.place_order.side_effect = lambda cmd: order_fn(cmd)
    return TradingOrchestrator(
        event_bus=bus,
        order_manager=om,
        strategy_evaluator=MagicMock(),
        feature_fetcher=MagicMock(),
        config=OrchestratorConfig(min_confidence=min_confidence),
        execution_engine=engine,
    )


def _ok_fn(cmd):
    return OrderResult(success=True, order=_FakeOrder("O1", cmd.correlation_id))


def test_execute_signal_publishes_plan_built_and_order_requested():
    bus = _Bus()
    orch = _orch(bus, order_fn=_ok_fn)
    orch._execute_signal(_signal(), "corr-1")

    types = [e.event_type for e in bus.events]
    assert EventType.EXECUTION_PLAN_BUILT.value in types
    assert EventType.ORDER_REQUESTED.value in types
    assert EventType.SIGNAL_EXECUTED.value in types
    assert EventType.RISK_APPROVED.value not in types
    assert orch.executed_count == 1


def test_execution_plan_built_event_is_typed_parseable():
    bus = _Bus()
    orch = _orch(bus, order_fn=_ok_fn)
    orch._execute_signal(_signal(), "corr-1")

    evt = next(e for e in bus.events if e.event_type == EventType.EXECUTION_PLAN_BUILT.value)
    typed = ExecutionPlanBuiltEvent.from_domain_event(evt)
    assert isinstance(typed.execution_plan, ExecutionPlan)
    assert typed.execution_plan.symbol == "RELIANCE"


def test_order_requested_event_is_typed_parseable():
    bus = _Bus()
    orch = _orch(bus, order_fn=_ok_fn)
    orch._execute_signal(_signal(), "corr-1")

    evt = next(e for e in bus.events if e.event_type == EventType.ORDER_REQUESTED.value)
    typed = OrderRequestedEvent.from_domain_event(evt)
    assert typed.request.symbol == "RELIANCE"
    assert typed.request.slicing_algo == "NONE"


def test_kill_switch_no_longer_pre_blocks_at_orchestrator():
    """Phase A: kill-switch enforcement lives in OMS, not orchestrator gating."""
    bus = _Bus()
    orch = _orch(bus, kill_switch=True, order_fn=_ok_fn)
    orch._execute_signal(_signal(), "corr-1")

    types = [e.event_type for e in bus.events]
    assert EventType.EXECUTION_PLAN_BUILT.value in types
    assert EventType.SIGNAL_EXECUTED.value in types
    assert orch.executed_count == 1


def test_low_confidence_is_rejected_before_plan():
    bus = _Bus()
    orch = _orch(bus, min_confidence=0.95, order_fn=_ok_fn)
    orch._execute_signal(_signal(confidence=Decimal("0.9")), "corr-1")

    types = [e.event_type for e in bus.events]
    assert EventType.EXECUTION_PLAN_BUILT.value not in types
    assert orch.rejected_count == 1


def test_eng003_refuses_signal_with_no_size():
    # No quantity, no position_size_pct -> plan has no legs -> rejected.
    bus = _Bus()
    orch = _orch(bus, order_fn=_ok_fn)
    orch._execute_signal(_signal(quantity=0, position_size_pct=Decimal("0")), "corr-1")

    types = [e.event_type for e in bus.events]
    assert EventType.ORDER_REQUESTED.value not in types
    assert EventType.SIGNAL_EXECUTED.value not in types
    assert orch.rejected_count == 1


def test_risk_rejection_does_not_publish_orchestrator_risk_rejected():
    def _fail(cmd):
        return OrderResult(success=False, error="position limit exceeded")

    bus = _Bus()
    orch = _orch(bus, order_fn=_fail)
    orch._execute_signal(_signal(), "corr-1")

    types = [e.event_type for e in bus.events]
    assert EventType.RISK_REJECTED.value not in types
    assert EventType.SIGNAL_EXECUTED.value not in types
    assert orch.rejected_count == 1
