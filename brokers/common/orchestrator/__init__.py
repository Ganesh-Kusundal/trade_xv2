"""Shim — use :mod:`application.trading`."""

from application.trading import (
    ExecutionRequest,
    ExecutionResult,
    FeatureFetcher,
    MultiStrategyRuntime,
    OrchestratorConfig,
    PipelineFeatureFetcher,
    TradingOrchestrator,
)

__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "FeatureFetcher",
    "MultiStrategyRuntime",
    "OrchestratorConfig",
    "PipelineFeatureFetcher",
    "TradingOrchestrator",
]
