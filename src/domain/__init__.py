"""Canonical domain layer — types, models, requests, and constants.

All cross-layer imports should use ``domain`` (or sub-packages).
"""

from __future__ import annotations

from domain.capabilities import Capability, ConnectionStatus
from domain.extensions import Extension, ExtensionRegistry
from domain.providers import DataProvider, ExecutionProvider, ProviderRegistry, SubscriptionHandle
from domain.ports.broker_adapter import BrokerAdapter
from domain.ports.bootstrap import BootstrapResult, BootstrapStatus
from domain.value_objects import (
    ExtensionInfo,
    InstrumentState,
    Money,
    SubscriptionState,
    TickSize,
)
from domain.entities import (
    Balance,
    ConditionalAlert,
    ConditionalAlertRequest,
    DepthLevel,
    FundLimits,
    FutureChain,
    FutureContract,
    Holding,
    Instrument,
    InstrumentRecord,
    MarketDepth,
    MarketIntelligenceSnapshot,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionStrike,
    Order,
    OrderResponse,
    PnlExitPolicy,
    PnlExitResult,
    Position,
    Quote,
    Trade,
)
from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from domain.market_enums import Exchange, ExchangeSegment, InstrumentType, OptionType
from domain.reconciliation import (
    DriftItem,
    ReconciliationReport,
)
from domain.orders.requests import (
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)
from domain.executions.result import GatewayResult, ResultMetadata
from domain.errors import TradeXV2RecoverableError
from domain.executions.execution import Execution
from domain.instruments.subscription import Subscription
from domain.universe import Session, Universe
from domain.portfolio.portfolio import Portfolio
from domain.risk.policy import (
    ConcentrationLimit,
    DailyLossCircuitBreaker,
    GrossExposureLimit,
    KillSwitch,
    OrderNotionalLimit,
    RiskGate,
    RiskResult,
)

__all__ = [
    # ── V2: Instrument-Centric Architecture ──────────────────────
    "DataProvider",
    "ExecutionProvider",
    "Extension",
    "ExtensionInfo",
    "ExtensionRegistry",
    "InstrumentState",
    "Money",
    "ProviderRegistry",
    "SubscriptionHandle",
    "SubscriptionState",
    "TickSize",
    # ── New domain objects (Phase 1) ────────────────────────────
    "Execution",
    "Session",
    "Universe",
    "TradeXV2RecoverableError",
    "BrokerAdapter",
    "BootstrapResult",
    "BootstrapStatus",
    # ── Phase 3: risk policies + Portfolio ───────────────────────
    "Portfolio",
    "RiskGate",
    "RiskResult",
    "OrderNotionalLimit",
    "ConcentrationLimit",
    "GrossExposureLimit",
    "DailyLossCircuitBreaker",
    "KillSwitch",
    # ── Legacy (kept for backward compat during migration) ──────
    "Balance",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    "DepthLevel",
    "DriftItem",
    "Exchange",
    "ExchangeSegment",
    "FundLimits",
    "FutureChain",
    "FutureContract",
    "GatewayResult",
    "Holding",
    "Instrument",
    "InstrumentRecord",
    "InstrumentType",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "ModifyOrderRequest",
    "OptionChain",
    "OptionType",
    "OptionContract",
    "OptionLeg",
    "OptionStrike",
    "Order",
    "OrderPreview",
    "OrderRequest",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "PnlExitPolicy",
    "PnlExitResult",
    "Position",
    "ProductType",
    "Quote",
    "ReconciliationReport",
    "ResultMetadata",
    "Side",
    "SliceOrderRequest",
    "Trade",
    "Validity",
]
