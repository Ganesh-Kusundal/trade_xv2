"""Domain ports — Protocols only; no I/O implementations.

NOTE: this package previously imported several port modules that were never
created (event_bus, fill_source, idempotency_guard, portfolio_model,
risk_model, data_adapter). Those imports were dead — nothing in src defines
or references them — so they have been dropped. Only the port modules that
actually exist on disk are re-exported here.
"""

from __future__ import annotations

from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.clock import Clock
from domain.ports.strategy import Strategy
from domain.ports.types import (
    BrokerSnapshot,
    CancelResult,
    IdempotencyResult,
    OrderResult,
    PortfolioContext,
    RiskContext,
    Signal,
    StartEvent,
    StopEvent,
    Subscription,
)

# Backward-compatible aliases for existing codebase references.
BrokerAdapterPort = BrokerAdapter

__all__ = [
    # Spec names
    "BrokerAdapter",
    "Clock",
    "Strategy",
    # Supporting types
    "BrokerSnapshot",
    "CancelResult",
    "IdempotencyResult",
    "OrderResult",
    "PortfolioContext",
    "RiskContext",
    "Signal",
    "StartEvent",
    "StopEvent",
    "Subscription",
    # Backward-compatible aliases
    "BrokerAdapterPort",
]
