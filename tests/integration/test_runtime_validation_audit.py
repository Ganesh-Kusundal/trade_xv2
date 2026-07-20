from __future__ import annotations
from tests.conftest import build_test_trading_context

from unittest.mock import MagicMock

import pytest

from tests.integration._strategy_pipeline_evaluator import StrategyPipelineEvaluator
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from application.oms.factory import create_trading_context
from domain.models.features import FeatureSet
from infrastructure.event_bus import DomainEvent, EventType
from infrastructure.lifecycle import LifecycleManager
from runtime.factory import BuildOptions, build_from_broker_service


class _StaticFeatureFetcher:
    def fetch(self, symbol: str) -> FeatureSet:
        return FeatureSet(columns={"close": [100.0, 101.0, 102.0, 103.0, 104.0]})


class _AlwaysBuyStrategy:
    name = "always_buy"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.BUY,
            confidence=0.95,
            strategy=self.name,
            entry_price=100.0,
        )


@pytest.fixture
def mock_broker_service():
    tc = build_test_trading_context(replay_events=False)
    bs = MagicMock()
    bs.active_broker = MagicMock()
    bs.trading_context = tc
    bs._gateway = None
    bs._upstox_gateway = None
    bs._active_name = "dhan"
    bs.lifecycle = LifecycleManager()
    bs.http_observability = None
    bs._readiness_report = None
    bs.live_actionable = False
    bs.active_broker_name = "mock"
    bs._event_bus = tc.event_bus
    return bs


def test_runtime_factory_bootstrap_and_orchestrator_event_flow(mock_broker_service) -> None:
    opts = BuildOptions(
        wire_orchestrator=True,
        orchestrator_dry_run=True,
        skip_parity_gate=True,
    )
    runtime = build_from_broker_service(mock_broker_service, options=opts)

    assert runtime.trading_context is not None
    assert runtime.event_bus is runtime.trading_context.event_bus
    assert runtime.trading_orchestrator is not None

    orch = runtime.trading_orchestrator
    orch._feature_fetcher = _StaticFeatureFetcher()
    orch._strategy_evaluator = StrategyPipelineEvaluator(
        StrategyPipeline(strategies=[_AlwaysBuyStrategy()])
    )
    # Also update the evaluator delegate so on_candidate uses the new references.
    orch._evaluator._feature_fetcher = orch._feature_fetcher
    orch._evaluator._strategy_evaluator = orch._strategy_evaluator

    event = DomainEvent.now(
        EventType.CANDIDATE_GENERATED.value,
        {"symbol": "RELIANCE", "score": 85.0},
        correlation_id="runtime-audit-1",
    )
    runtime.trading_context.event_bus.publish(event)

    assert orch.executed_count + orch.rejected_count > 0


def test_runtime_factory_exposes_real_oms_components(mock_broker_service) -> None:
    opts = BuildOptions(skip_parity_gate=True)
    build_from_broker_service(mock_broker_service, options=opts)
