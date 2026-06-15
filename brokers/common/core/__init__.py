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
from brokers.common.core.domain import BrokerConnection, Capability, ConnectionStatus
from brokers.common.core.domain import (
    ExchangeSegment,
    FeedMode,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.instruments import Instrument, InstrumentRegistry
from brokers.common.core.domain import (
    ConditionalAlert,
    ConditionalAlertRequest,
    FundLimits,
    HistoricalCandle,
    Holding,
    MarketDepth,
    MarketDepthLevel,
    ModifyOrderRequest,
    OptionContract,
    Order,
    OrderPreview,
    OrderRequest,
    OrderResponse,
    PnlExitPolicy,
    PnlExitResult,
    Position,
    Quote,
    SliceOrderRequest,
    Trade,
)
from brokers.common.core.result import GatewayResult, ResultMetadata

__all__ = [
    # Auth
    "AuthManager",
    # Connection
    "BrokerConnection",
    "Capability",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    "EnvTokenStateStore",
    # Enums
    "ExchangeSegment",
    "FeedMode",
    "FundLimits",
    # Result
    "GatewayResult",
    "HistoricalCandle",
    "Holding",
    # Instruments
    "Instrument",
    "InstrumentRegistry",
    "InstrumentType",
    "JsonTokenStateStore",
    "MarketDepth",
    "MarketDepthLevel",
    "ModifyOrderRequest",
    "OptionContract",
    # Models
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
    "ResultMetadata",
    "SliceOrderRequest",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "Trade",
    "TransactionType",
    "Validity",
]
