"""G7 — kill switch reads via injected RiskManagerPort, not getattr reach-through.

Regression guard: TradingOrchestrator._is_kill_switch_active must consult the
injected RiskManagerPort, never reach into order_manager.risk_manager via getattr.
If it did, an injected manager would be ignored and a rename of the internal
attribute would silently break the kill switch.
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
        risk_manager=risk_manager,
    )


def test_injected_risk_manager_is_used_over_order_manager_attribute() -> None:
    injected = mock.MagicMock(spec=RiskManagerPort)
    injected.is_kill_switch_active.return_value = True

    # order_manager.risk_manager returns a DIFFERENT object — must be ignored.
    orch = _build(risk_manager=injected)
    assert orch._is_kill_switch_active() is True
    injected.is_kill_switch_active.assert_called_once()

    # The old reach-through would call order_manager.risk_manager; ensure it did not.
    orch._order_manager.risk_manager.assert_not_called()


def test_kill_switch_inactive_when_no_risk_manager() -> None:
    order_manager = mock.MagicMock()
    order_manager.risk_manager = None  # neither injected nor on order manager
    orch = TradingOrchestrator(
        event_bus=mock.MagicMock(),
        order_manager=order_manager,
        strategy_evaluator=mock.MagicMock(),
        feature_fetcher=mock.MagicMock(),
        config=OrchestratorConfig(),
        risk_manager=None,
    )
    assert orch._is_kill_switch_active() is False


def test_kill_switch_reflects_injected_state() -> None:
    inactive = mock.MagicMock(spec=RiskManagerPort)
    inactive.is_kill_switch_active.return_value = False
    orch = _build(risk_manager=inactive)
    assert orch._is_kill_switch_active() is False
