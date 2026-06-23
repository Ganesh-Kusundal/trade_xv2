"""Shim — use :mod:`brokers.common.execution.trading_orchestrator` (REF-16)."""

from brokers.common.execution.trading_orchestrator import (
    OrchestratorConfig,
    TradingOrchestrator,
)

__all__ = ["OrchestratorConfig", "TradingOrchestrator"]
