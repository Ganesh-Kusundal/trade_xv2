"""Domain ports — Protocols only; no I/O implementations."""

from __future__ import annotations

from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.clock import Clock
from domain.ports.data_adapter import DataAdapter
from domain.ports.event_bus import EventBusPort
from domain.ports.fill_source import FillSource
from domain.ports.idempotency_guard import IdempotencyGuard
from domain.ports.portfolio_model import PortfolioModel
from domain.ports.risk_model import RiskModel
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
DataCatalogPort = DataAdapter
FillSourcePort = FillSource
RiskEnginePort = RiskModel

__all__ = [
    # New spec names
    "BrokerAdapter",
    "Clock",
    "DataAdapter",
    "EventBusPort",
    "FillSource",
    "IdempotencyGuard",
    "PortfolioModel",
    "RiskModel",
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
    "DataCatalogPort",
    "FillSourcePort",
    "RiskEnginePort",
]
