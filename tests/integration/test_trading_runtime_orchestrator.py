"""Integration test: Runtime factory orchestrator handles CANDIDATE_GENERATED.

REF: Task 6.3 — Converted from MagicMock to FakeTradingOrchestrator and protocol-compliant fakes
"""

from __future__ import annotations

import pytest

from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from domain.models.features import FeatureSet
from infrastructure.event_bus import DomainEvent, EventType
from infrastructure.lifecycle import LifecycleManager
from runtime.factory import BuildOptions, build_from_broker_service
from tests.conftest import build_test_trading_context
from tests.integration._strategy_pipeline_evaluator import StrategyPipelineEvaluator


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
    # REF: Using real TradingContext instead of MagicMock for critical parts
    tc = build_test_trading_context(replay_events=False)

    # Use a minimal mock only for non-critical broker-specific attributes
    from unittest.mock import MagicMock

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


def test_candidate_generated_increments_orchestrator_counter(mock_broker_service) -> None:
    opts = BuildOptions(
        wire_orchestrator=True,
        orchestrator_dry_run=True,
        skip_parity_gate=True,
    )
    runtime = build_from_broker_service(mock_broker_service, options=opts)
    orch = runtime.trading_orchestrator
    assert orch is not None

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
        correlation_id="test-corr-1",
    )
    runtime.trading_context.event_bus.publish(event)

    assert orch.executed_count + orch.rejected_count > 0
