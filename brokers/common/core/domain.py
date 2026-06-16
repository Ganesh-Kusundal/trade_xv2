"""Canonical domain — re-export facade.

This module is a **thin re-export layer** that preserves backward
compatibility for every ``from brokers.common.core.domain import ...``
statement in the codebase. The actual definitions live in focused
sub-modules:

* :mod:`brokers.common.core.types` — enums (``Side``, ``OrderStatus``, etc.)
* :mod:`brokers.common.core.models` — domain dataclasses (``Order``, ``Position``, etc.)
* :mod:`brokers.common.core.requests` — input shapes (``OrderRequest``, etc.)
* :mod:`brokers.common.core.reconciliation` — drift/reconciliation types

New code SHOULD import from the specific sub-modules directly.
Existing code that imports from this module continues to work unchanged.
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


# ── BrokerConnection (re-exported from spi.py for backward compatibility) ──
from brokers.common.api.spi import BrokerConnection  # noqa: F401
