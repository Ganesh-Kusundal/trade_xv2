"""TradingOrchestrator lifecycle: event subscription ownership on start/stop."""

from __future__ import annotations

from unittest import mock

from application.trading.trading_orchestrator import OrchestratorConfig, TradingOrchestrator
from infrastructure.event_bus import EventType


def test_start_subscribes_and_stop_unsubscribes_from_candidate_events() -> None:
    bus = mock.MagicMock()
    bus.subscribe.return_value = "subscription-token-1"

    orchestrator = TradingOrchestrator(
        event_bus=bus,
        order_manager=mock.MagicMock(),
        strategy_evaluator=mock.MagicMock(),
        feature_fetcher=mock.MagicMock(),
        config=OrchestratorConfig(),
    )

    orchestrator.start()
    bus.subscribe.assert_called_once_with(
        EventType.CANDIDATE_GENERATED.value,
        orchestrator.on_candidate,
    )

    orchestrator.stop()
    bus.unsubscribe.assert_called_once_with("subscription-token-1")
    assert orchestrator._candidate_subscription_token is None


def test_start_is_idempotent_when_already_subscribed() -> None:
    bus = mock.MagicMock()
    bus.subscribe.return_value = "subscription-token-1"

    orchestrator = TradingOrchestrator(
        event_bus=bus,
        order_manager=mock.MagicMock(),
        strategy_evaluator=mock.MagicMock(),
        feature_fetcher=mock.MagicMock(),
        config=OrchestratorConfig(),
    )

    orchestrator.attach_event_subscription()
    orchestrator.start()

    bus.subscribe.assert_called_once()
