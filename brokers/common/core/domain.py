"""Canonical domain — public re-export facade.

This module is the canonical import path for all domain types that cross
adapter, OMS, CLI, analytics, and test boundaries. Concrete dataclass
definitions live in focused sub-modules:

* :mod:`brokers.common.core.types` — enums (``Side``, ``OrderStatus``, etc.)
* :mod:`brokers.common.core.models` — canonical dataclasses
* :mod:`brokers.common.core.requests` — input shapes (``OrderRequest``, etc.)
* :mod:`brokers.common.core.reconciliation` — drift/reconciliation types

All new code should import from this module to keep the adapter boundary
explicit.
"""

from __future__ import annotations

# ── Re-exports: enums (from types.py) ─────────────────────────────────────
from brokers.common.core.types import (  # noqa: F401
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

# ── Re-exports: domain models (from models.py) ────────────────────────────
from brokers.common.core.models import (  # noqa: F401
    Balance,
    ConditionalAlert,
    ConditionalAlertRequest,
    DepthLevel,
    FundLimits,
    Holding,
    Instrument,
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

# ── Re-exports: request/input shapes (from requests.py) ───────────────────
from brokers.common.core.requests import (  # noqa: F401
    HistoricalCandle,
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)

# ── Re-exports: reconciliation types (from reconciliation.py) ─────────────
from brokers.common.core.reconciliation import (  # noqa: F401
    DriftItem,
    ReconciliationReport,
)

