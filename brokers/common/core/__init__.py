"""Core module — domain enums, data models, result type, connection interface."""

from __future__ import annotations

from brokers.common.core.auth import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
)
from brokers.common.core.domain import BrokerConnection
from brokers.common.core.instruments import Instrument, InstrumentRegistry
from brokers.common.core.domain import (
    Balance,
    ConditionalAlert,
    ConditionalAlertRequest,
    DepthLevel,
    FundLimits,
    Holding,
    MarketDepth,
    MarketIntelligenceSnapshot,
    OptionContract,
    Order,
    OrderResponse,
    PnlExitPolicy,
    PnlExitResult,
    Position,
    Quote,
    Trade,
)
from brokers.common.core.pnl_calculator import PnLCalculator, PnLSnapshot
from brokers.common.core.reconciliation import (
    DriftItem,
    ReconciliationReport,
)
from brokers.common.core.requests import (
    HistoricalCandle,
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)
from brokers.common.core.result import GatewayResult, ResultMetadata
from brokers.common.core.types import (
    Capability,
    ConnectionStatus,
    ExchangeSegment,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)

__all__ = [
    "AuthManager",
    "Balance",
    "BrokerConnection",
    "Capability",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    "DepthLevel",
    "DriftItem",
    "EnvTokenStateStore",
    "ExchangeSegment",
    "FundLimits",
    "GatewayResult",
    "HistoricalCandle",
    "Holding",
    "Instrument",
    "InstrumentRegistry",
    "InstrumentType",
    "JsonTokenStateStore",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "ModifyOrderRequest",
    "OptionContract",
    "Order",
    "OrderPreview",
    "OrderRequest",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "PnLCalculator",
    "PnLSnapshot",
    "PnlCalculator",
    "PnlExitPolicy",
    "PnlExitResult",
    "Position",
    "ProductType",
    "Quote",
    "ReconciliationReport",
    "ResultMetadata",
    "Side",
    "SliceOrderRequest",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "Trade",
    "Validity",
]
