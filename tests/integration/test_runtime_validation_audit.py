from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from infrastructure.event_bus import DomainEvent, EventType
from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms.factory import create_trading_context
from runtime.trading_runtime_factory import TradingRuntimeFactory


class _StaticFeatureFetcher:
    def fetch(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]})


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
    tc = create_trading_context(replay_events=False)
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
    factory = TradingRuntimeFactory(
        wire_orchestrator=True,
        orchestrator_dry_run=True,
        skip_parity_gate=True,
    )
    runtime = factory.build_from_broker_service(mock_broker_service)

    assert runtime.trading_context is not None
    assert runtime.event_bus is runtime.trading_context.event_bus
    assert runtime.trading_orchestrator is not None

    orch = runtime.trading_orchestrator
    orch._feature_fetcher = _StaticFeatureFetcher()
    orch._strategy_pipeline = StrategyPipeline(strategies=[_AlwaysBuyStrategy()])

    event = DomainEvent.now(
        EventType.CANDIDATE_GENERATED.value,
        {"symbol": "RELIANCE", "score": 85.0},
        correlation_id="runtime-audit-1",
    )
    runtime.trading_context.event_bus.publish(event)

    assert orch.executed_count + orch.rejected_count > 0


def test_runtime_factory_exposes_real_oms_components(mock_broker_service) -> None:
    factory = TradingRuntimeFactory(skip_parity_gate=True)
    runtime = factory.build_from_broker_service(mock_broker_service)

    assert runtime.order_manager is not None
    assert runtime.risk_manager is not None
    assert runtime.position_manager is not None
    assert runtime.trading_context is not None
