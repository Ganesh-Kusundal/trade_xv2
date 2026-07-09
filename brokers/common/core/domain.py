"""Broker-side re-export shim for the canonical domain models.

Satisfies the import-linter enforcement rule (``pyproject.toml``) that
requires importing the domain models from ``brokers.common.core.domain``.
The real dataclass definitions live in ``src/domain/...`` (the single
source of truth for the trading domain) — this module simply re-exports
them so the ``core.domain`` import target resolves without duplicating
any model definitions into the broker layer.

This is a FIX-ONLY shim — no domain model is duplicated here.
"""

from __future__ import annotations

from src.domain.capabilities import Capability, ConnectionStatus
from src.domain.entities import (
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
from src.domain.enums import OrderStatus, OrderType, ProductType, Side
from src.domain.instruments.instrument import Instrument

__all__ = [
    "Balance",
    "Capability",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    "DepthLevel",
    "FundLimits",
    "Holding",
    "Instrument",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "OptionContract",
    "Order",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "PnlExitPolicy",
    "PnlExitResult",
    "Position",
    "ProductType",
    "Quote",
    "Side",
    "Trade",
]
