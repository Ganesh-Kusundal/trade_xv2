"""Canonical domain layer — types, models, requests, and constants.

All cross-layer imports should use ``domain`` (or sub-packages).
"""

from __future__ import annotations

from domain.capabilities import Capability, ConnectionStatus
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
from domain.exceptions import TradeXV2RecoverableError
from domain.executions.execution import Execution
from domain.executions.result import GatewayResult, ResultMetadata
from domain.extensions import Extension, ExtensionRegistry
from domain.instruments.subscription import Subscription
from domain.market_enums import Exchange, ExchangeSegment, InstrumentType, OptionType
from domain.orders.requests import (
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)
from domain.portfolio.portfolio import Portfolio
from domain.ports.bootstrap import BootstrapResult, BootstrapStatus
from domain.ports.broker_adapter import BrokerAdapter
from domain.providers import DataProvider, ExecutionProvider, ProviderRegistry, SubscriptionHandle
from domain.reconciliation import (
    DriftItem,
    ReconciliationReport,
)
from domain.risk.policy import (
    ConcentrationLimit,
    DailyLossCircuitBreaker,
    GrossExposureLimit,
    KillSwitch,
    OrderNotionalLimit,
    RiskGate,
    RiskResult,
)
from domain.universe import Session, Universe
from domain.value_objects import (
    ExtensionInfo,
    InstrumentState,
    Money,
    SubscriptionState,
    TickSize,
)

__all__ = [
    # ── Legacy (kept for backward compat during migration) ──────
    "Balance",
    "BootstrapResult",
    "BootstrapStatus",
    "BrokerAdapter",
    "ConcentrationLimit",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    "DailyLossCircuitBreaker",
    # ── V2: Instrument-Centric Architecture ──────────────────────
    "DataProvider",
    "DepthLevel",
    "DriftItem",
    "Exchange",
    "ExchangeSegment",
    # ── New domain objects (Phase 1) ────────────────────────────
    "Execution",
    "ExecutionProvider",
    "Extension",
    "ExtensionInfo",
    "ExtensionRegistry",
    "FundLimits",
    "FutureChain",
    "FutureContract",
    "GatewayResult",
    "GrossExposureLimit",
    "Holding",
    "Instrument",
    "InstrumentRecord",
    "InstrumentState",
    "InstrumentType",
    "KillSwitch",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "ModifyOrderRequest",
    "Money",
    "OptionChain",
    "OptionContract",
    "OptionLeg",
    "OptionStrike",
    "OptionType",
    "Order",
    "OrderNotionalLimit",
    "OrderPreview",
    "OrderRequest",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "PnlExitPolicy",
    "PnlExitResult",
    # ── Phase 3: risk policies + Portfolio ───────────────────────
    "Portfolio",
    "Position",
    "ProductType",
    "ProviderRegistry",
    "Quote",
    "ReconciliationReport",
    "ResultMetadata",
    "RiskGate",
    "RiskResult",
    "Session",
    "Side",
    "SliceOrderRequest",
    "SubscriptionHandle",
    "SubscriptionState",
    "TickSize",
    "Trade",
    "TradeXV2RecoverableError",
    "Universe",
    "Validity",
]
