"""Trading orchestrator — connects Scanner→Strategy→OMS execution path.

The TradingOrchestrator is the missing link between the analytics layer
(scanner/strategy) and the execution layer (OMS/broker). It:

1. Subscribes to CANDIDATE_GENERATED events from the EventBus
2. Fetches feature data for each candidate via FeatureFetcher
3. Evaluates candidates through StrategyPipeline
4. Converts actionable signals to OmsOrderCommand
5. Places orders through OrderManager
6. Publishes RISK_APPROVED/RISK_REJECTED events based on OMS result

Usage:
    orchestrator = TradingOrchestrator(
        event_bus=bus,
        order_manager=oms.order_manager,
        strategy_pipeline=strategy_pipeline,
        feature_fetcher=feature_fetcher,
        min_confidence=0.7,
        dry_run=False,
    )
    event_bus.subscribe(EventType.CANDIDATE_GENERATED, orchestrator.on_candidate)
    lifecycle_manager.register(orchestrator)
"""

from __future__ import annotations

from brokers.common.orchestrator.models import (
    ExecutionRequest,
    ExecutionResult,
    FeatureFetcher,
)
from brokers.common.orchestrator.trading_orchestrator import TradingOrchestrator

__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "FeatureFetcher",
    "TradingOrchestrator",
]
