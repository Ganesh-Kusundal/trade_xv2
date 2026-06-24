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

# Re-export types for backward compatibility (old domain/entities.py
# imported these at module level, so `from domain.entities import OrderStatus`
# was valid). New code should import from domain.types directly.
from domain.types import (  # noqa: F401
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)

# Order-related
from domain.entities.order import (  # noqa: F401
    FieldMapping,
    Order,
    OrderResponse,
)
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS  # noqa: F401

# Trade
from domain.entities.trade import Trade  # noqa: F401

# Position / Holding
from domain.entities.position import (  # noqa: F401
    Holding,
    Position,
)

# Account (REF-024: FundLimits consolidated into Balance)
from domain.entities.account import (  # noqa: F401
    Balance,
    FundLimits,
)

# Market data
from domain.entities.market import (  # noqa: F401
    DepthLevel,
    MarketDepth,
    Quote,
)

# Instrument (REF-027: frozen)
from domain.entities.instrument import Instrument  # noqa: F401

# Options / Futures
from domain.entities.options import (  # noqa: F401
    FutureChain,
    FutureContract,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionStrike,
)

# Alerts / PnL (REF-027: frozen where applicable)
from domain.entities.alerts import (  # noqa: F401
    ConditionalAlert,
    ConditionalAlertRequest,
    MarketIntelligenceSnapshot,
    PnlExitPolicy,
    PnlExitResult,
)
