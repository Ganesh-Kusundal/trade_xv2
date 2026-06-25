"""Canonical domain dataclasses — value objects returned by broker adapters.

This package re-exports all entities for backward compatibility::

    from domain.entities import Order, Position, Balance

The individual sub-modules are::

    domain.entities.order      — Order, OrderResponse, FieldMapping
    domain.entities.order_lifecycle — ORDER_STATUS_TRANSITIONS
    domain.entities.trade      — Trade
    domain.entities.position   — Position, Holding
    domain.entities.account    — Balance, FundLimits (alias)
    domain.entities.market     — Quote, MarketDepth, DepthLevel
    domain.entities.options    — OptionChain, OptionStrike, OptionLeg, FutureChain, FutureContract, OptionContract
    domain.entities.instrument — Instrument
    domain.entities.alerts     — ConditionalAlert, ConditionalAlertRequest, MarketIntelligenceSnapshot, PnlExitPolicy, PnlExitResult
"""

from __future__ import annotations

# Account (REF-024: FundLimits consolidated into Balance)
from domain.entities.account import (
    Balance,
    FundLimits,
)

# Alerts / PnL (REF-027: frozen where applicable)
from domain.entities.alerts import (
    ConditionalAlert,
    ConditionalAlertRequest,
    MarketIntelligenceSnapshot,
    PnlExitPolicy,
    PnlExitResult,
)

# Instrument (REF-027: frozen)
from domain.entities.instrument import Instrument

# Market data
from domain.entities.market import (
    DepthLevel,
    MarketDepth,
    Quote,
)

# Options / Futures
from domain.entities.options import (
    FutureChain,
    FutureContract,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionStrike,
)

# Order-related
from domain.entities.order import (
    FieldMapping,
    Order,
    OrderResponse,
)
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS

# Position / Holding
from domain.entities.position import (
    Holding,
    Position,
)

# Trade
from domain.entities.trade import Trade

# Re-export types for backward compatibility (old domain/entities.py
# imported these at module level, so `from domain.entities import OrderStatus`
# was valid). New code should import from domain.types directly.
from domain.types import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)

__all__ = [
    "ORDER_STATUS_TRANSITIONS",
    "Balance",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "DepthLevel",
    "FieldMapping",
    "FundLimits",
    "FutureChain",
    "FutureContract",
    "Holding",
    "Instrument",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "OptionChain",
    "OptionContract",
    "OptionLeg",
    "OptionStrike",
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
    "Validity",
]
