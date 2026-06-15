"""Frozen data contracts for broker-agnostic market data.

These are the ONLY schemas allowed in consumer-facing code.
No broker-specific fields are permitted.

All canonical types are defined in brokers.common.core.domain.
This module re-exports them for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core.domain import (  # noqa: F401 — re-exports
    Balance,
    ConditionalAlert,
    ConditionalAlertRequest,
    DepthLevel,
    FundLimits,
    Holding,
    Instrument,
    MarketDepth,
    MarketDepthLevel,
    MarketIntelligenceSnapshot,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    OptionContract,
    Position,
    PnlExitPolicy,
    PnlExitResult,
    ProductType,
    Quote,
    Side,
    SliceOrderRequest,
    Trade,
    TransactionType,
    Validity,
)


# ── Historical DataFrame Contract ──────────────────────────────────────────

HISTORICAL_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "symbol",
    "exchange",
    "timeframe",
]


def validate_historical_df(df: pd.DataFrame) -> bool:
    """Validate DataFrame matches frozen historical schema."""
    return list(df.columns) == HISTORICAL_COLUMNS


# ── Option Chain Contract ──────────────────────────────────────────────────

OPTION_CHAIN_COLUMNS = [
    "expiry",
    "strike",
    "option_type",
    "ltp",
    "volume",
    "oi",
    "iv",
]


# ── Future Chain Contract ──────────────────────────────────────────────────

FUTURE_CHAIN_COLUMNS = [
    "expiry",
    "ltp",
    "volume",
    "oi",
    "change",
]


# ── Validation Helpers ─────────────────────────────────────────────────────

QUOTE_FIELDS = list(Quote.__dataclass_fields__.keys())

FORBIDDEN_FIELDS = [
    "security_id",
    "instrument_token",
    "exchange_token",
    "symbol_token",
    "raw_json",
    "raw_api_response",
]


def validate_no_forbidden_fields(obj: Any) -> bool:
    """Check that an object has no broker-specific fields."""
    if hasattr(obj, "__dataclass_fields__"):
        fields = list(obj.__dataclass_fields__.keys())
    elif hasattr(obj, "__dict__"):
        fields = list(obj.__dict__.keys())
    else:
        return True
    return not any(f in fields for f in FORBIDDEN_FIELDS)
