"""Canonical domain layer — types, models, requests, and constants.

All cross-layer imports should use ``domain`` (or sub-packages) rather than
``brokers.common.core``.  ``brokers.common.core`` re-exports with deprecation
warnings for one release cycle.
"""

from __future__ import annotations

from domain.types import (  # noqa: F401
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
from domain.entities import (  # noqa: F401
    Balance,
    ConditionalAlert,
    ConditionalAlertRequest,
    DepthLevel,
    FundLimits,
    FutureChain,
    FutureContract,
    Holding,
    Instrument,
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
from domain.requests import (  # noqa: F401
    HistoricalCandle,
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)
from domain.reconciliation import (  # noqa: F401
    DriftItem,
    ReconciliationReport,
)
from domain.result import GatewayResult, ResultMetadata  # noqa: F401

__all__ = [
    "Balance",
    "Capability",
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
