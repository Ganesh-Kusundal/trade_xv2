"""G7 — kill switch enforcement lives in OMS OrderMutationGuard, not orchestrator.

Regression guard: TradingOrchestrator must not reach into order_manager.risk_manager
via getattr for kill-switch checks. Enforcement is centralized in
``OrderLifecycle`` via ``OrderMutationGuard``.
"""

from __future__ import annotations

from unittest import mock

from application.trading.trading_orchestrator import OrchestratorConfig, TradingOrchestrator
from domain.ports.risk_manager import RiskManagerPort


def _build(risk_manager: RiskManagerPort | None = None) -> TradingOrchestrator:
    order_manager = mock.MagicMock()
    return TradingOrchestrator(
        event_bus=mock.MagicMock(),
        order_manager=order_manager,
        strategy_evaluator=mock.MagicMock(),
        feature_fetcher=mock.MagicMock(),
        config=OrchestratorConfig(),
        execution_engine=mock.MagicMock(),
        risk_manager=risk_manager,
    )


def test_orchestrator_does_not_expose_kill_switch_helper() -> None:
    """Kill-switch checks removed from orchestrator (Phase A — OMS owns policy)."""
    orch = _build(risk_manager=mock.MagicMock(spec=RiskManagerPort))
    assert not hasattr(orch, "_is_kill_switch_active")


def test_orchestrator_stores_injected_risk_manager() -> None:
    injected = mock.MagicMock(spec=RiskManagerPort)
    orch = _build(risk_manager=injected)
    assert orch._risk_manager is injected
    orch._order_manager.risk_manager.assert_not_called()


def test_orchestrator_without_risk_manager() -> None:
    order_manager = mock.MagicMock()
    order_manager.risk_manager = None
    orch = TradingOrchestrator(
        event_bus=mock.MagicMock(),
        order_manager=order_manager,
        strategy_evaluator=mock.MagicMock(),
        feature_fetcher=mock.MagicMock(),
        config=OrchestratorConfig(),
        execution_engine=mock.MagicMock(),
        risk_manager=None,
    )
    assert orch._risk_manager is None
