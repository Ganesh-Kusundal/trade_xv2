"""Canonical domain layer — types, models, requests, and constants.

All cross-layer imports should use ``domain`` (or sub-packages) rather than
``brokers.common.core``.  ``brokers.common.core`` re-exports with deprecation
warnings for one release cycle.
"""

from __future__ import annotations

from domain.capabilities import Capability, ConnectionStatus
from domain.aggregates import InstrumentAggregate
from domain.extensions import Extension, ExtensionRegistry
from domain.providers import DataProvider, ExecutionProvider, ProviderRegistry, Subscription
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
from domain.market_enums import ExchangeSegment, InstrumentType
from domain.reconciliation import (
    DriftItem,
    ReconciliationReport,
)
from domain.requests import (
    HistoricalCandle,
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)
from domain.result import GatewayResult, ResultMetadata

__all__ = [
    # ── V2: Instrument-Centric Architecture ──────────────────────
    "DataProvider",
    "ExecutionProvider",
    "Extension",
    "ExtensionInfo",
    "ExtensionRegistry",
    "InstrumentAggregate",
    "InstrumentState",
    "Money",
    "ProviderRegistry",
    "Subscription",
    "SubscriptionState",
    "TickSize",
    # ── Legacy (kept for backward compat during migration) ──────
    "Balance",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    "DepthLevel",
    "DriftItem",
    "ExchangeSegment",
    "FundLimits",
    "FutureChain",
    "FutureContract",
    "GatewayResult",
    "HistoricalCandle",
    "Holding",
    "Instrument",
    "InstrumentRecord",
    "InstrumentType",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "ModifyOrderRequest",
    "OptionChain",
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
