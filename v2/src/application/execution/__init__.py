"""Execution package — FillSources + ExecutionEngine (zero-parity spine)."""

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_sources import (
    BrokerFillSource,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
)
from application.execution.order_store import InMemoryOrderStore
from application.execution.protocols import (
    FillSource,
    IdempotencyGuard,
    RiskCheckResult,
    RiskManager,
)

__all__ = [
    "BrokerFillSource",
    "ExecutionEngine",
    "FillSource",
    "IdempotencyGuard",
    "InMemoryOrderStore",
    "PaperFillSource",
    "ReplayFillSource",
    "RiskCheckResult",
    "RiskManager",
    "SimulatedFillSource",
]
