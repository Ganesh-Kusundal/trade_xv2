"""End-to-end TradingOrchestrator test with real EventBus, OMS, and PaperGateway.

No mocks on OrderManager or ExecutionService — verifies the full
CANDIDATE_GENERATED → strategy → OMS → paper fill path.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from application.execution.execution_service import ExecutionService
from application.oms.context import TradingContext
from application.trading.trading_orchestrator import OrchestratorConfig, TradingOrchestrator
from brokers.paper.paper_gateway import PaperGateway
from domain.models.trading import CandidateDTO, SignalDTO
from infrastructure.event_bus import DomainEvent, EventType


class _StaticFeatureFetcher:
    """Returns minimal OHLCV features without external data."""

    def fetch(self, symbol: str, exchange: str = "NSE") -> pd.DataFrame:
        return pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.0, 103.0, 104.0],
                "open": [99.0, 100.0, 101.0, 102.0, 103.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [98.0, 99.0, 100.0, 101.0, 102.0],
                "volume": [1000, 1100, 1200, 1300, 1400],
            }
        )


class _AlwaysBuyEvaluator:
    """Strategy evaluator that always emits an actionable BUY signal."""

    def evaluate_single(self, candidate: CandidateDTO, features: pd.DataFrame) -> list[SignalDTO]:
        return [
            SignalDTO(
                symbol=candidate.symbol,
                exchange=candidate.exchange,
                side="BUY",
                signal_type="BUY",
                confidence=Decimal("0.95"),
                quantity=1,
                entry_price=Decimal("100"),
                strategy="test_always_buy",
            )
        ]


@pytest.fixture
def fresh_trading_context():
    return TradingContext(replay_events=False, enable_durable_orders=False)


def test_orchestrator_places_order_via_paper_gateway(fresh_trading_context) -> None:
    tc = fresh_trading_context
    paper = PaperGateway(trading_context=tc)
    exec_svc = ExecutionService(trading_context=tc, gateway=paper, mode="paper")
    orch = TradingOrchestrator(
        event_bus=tc.event_bus,
        order_manager=tc.order_manager,
        strategy_evaluator=_AlwaysBuyEvaluator(),
        feature_fetcher=_StaticFeatureFetcher(),
        config=OrchestratorConfig(min_confidence=0.7, dry_run=False),
        execution_service=exec_svc,
    )
    tc.event_bus.subscribe(EventType.CANDIDATE_GENERATED.value, orch.on_candidate)
    correlation_id = "e2e-orchestrator-corr-1"

    event = DomainEvent.now(
        EventType.CANDIDATE_GENERATED.value,
        {"symbol": "RELIANCE", "score": 85.0, "exchange": "NSE"},
        correlation_id=correlation_id,
    )
    tc.event_bus.publish(event)

    assert orch.executed_count == 1
    assert orch.error_count == 0

    orders = tc.order_manager.get_orders()
    assert len(orders) >= 1
    placed = orders[0]
    assert placed.symbol == "RELIANCE"
    assert placed.correlation_id.startswith(correlation_id)


def test_orchestrator_dry_run_does_not_place_orders(fresh_trading_context) -> None:
    tc = fresh_trading_context
    orch = TradingOrchestrator(
        event_bus=tc.event_bus,
        order_manager=tc.order_manager,
        strategy_evaluator=_AlwaysBuyEvaluator(),
        feature_fetcher=_StaticFeatureFetcher(),
        config=OrchestratorConfig(min_confidence=0.7, dry_run=True),
    )
    tc.event_bus.subscribe(EventType.CANDIDATE_GENERATED.value, orch.on_candidate)

    event = DomainEvent.now(
        EventType.CANDIDATE_GENERATED.value,
        {"symbol": "INFY", "score": 90.0},
        correlation_id="e2e-dry-run-1",
    )
    tc.event_bus.publish(event)

    assert orch.executed_count == 1
    assert tc.order_manager.get_orders() == []


def test_orchestrator_rejects_low_confidence(fresh_trading_context) -> None:
    tc = fresh_trading_context

    class _LowConfidenceEvaluator:
        def evaluate_single(self, candidate, features):
            return [
                SignalDTO(
                    symbol=candidate.symbol,
                    exchange=candidate.exchange,
                    side="BUY",
                    signal_type="BUY",
                    confidence=Decimal("0.1"),
                    quantity=1,
                    strategy="low_conf",
                )
            ]

    orch = TradingOrchestrator(
        event_bus=tc.event_bus,
        order_manager=tc.order_manager,
        strategy_evaluator=_LowConfidenceEvaluator(),
        feature_fetcher=_StaticFeatureFetcher(),
        config=OrchestratorConfig(min_confidence=0.7, dry_run=False),
    )
    tc.event_bus.subscribe(EventType.CANDIDATE_GENERATED.value, orch.on_candidate)

    event = DomainEvent.now(
        EventType.CANDIDATE_GENERATED.value,
        {"symbol": "TCS", "score": 50.0},
        correlation_id="e2e-low-conf-1",
    )
    tc.event_bus.publish(event)

    assert orch.rejected_count == 1
    assert tc.order_manager.get_orders() == []
