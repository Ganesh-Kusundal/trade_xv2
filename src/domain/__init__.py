"""Domain layer — canonical types and entities for TradeXV2.

This module re-exports the most commonly used domain types for backward
compatibility. New code should import from the owning submodule directly
(e.g., ``from domain.enums import Side``).

Backward-compatible re-exports maintained for the ~200 test files that
still use ``from domain import X`` until they are gradually migrated.
"""

from __future__ import annotations

__version__ = "0.1.0"

# ── Entities ──────────────────────────────────────────────────────────
from domain.entities import (
    Balance,
    DepthLevel,
    FundLimits,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)

# ── Enums ─────────────────────────────────────────────────────────────
from domain.enums import (
    OrderStatus,
    OrderType,
    PositionSide,
    ProductType,
    Side,
    Validity,
)

# ── Market enums ──────────────────────────────────────────────────────
from domain.market_enums import (
    Exchange,
    ExchangeId,
    ExchangeSegment,
    InstrumentType,
    OptionType,
)

# ── Capabilities ──────────────────────────────────────────────────────
from domain.capabilities.enums import (
    Capability,
    ConnectionStatus,
)

# ── Orders ────────────────────────────────────────────────────────────
from domain.orders.requests import OrderRequest

# ── Reconciliation ───────────────────────────────────────────────────
from domain.reconciliation import (
    DriftItem,
    ReconciliationReport,
)

# ── Public API surface ────────────────────────────────────────────────
__all__ = [
    "Balance",
    "Capability",
    "ConnectionStatus",
    "DepthLevel",
    "DriftItem",
    "Exchange",
    "ExchangeId",
    "ExchangeSegment",
    "FundLimits",
    "FutureChain",
    "Holding",
    "InstrumentType",
    "MarketDepth",
    "OptionChain",
    "OptionType",
    "Order",
    "OrderRequest",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "ProductType",
    "Quote",
    "ReconciliationReport",
    "Side",
    "Trade",
    "Validity",
]
