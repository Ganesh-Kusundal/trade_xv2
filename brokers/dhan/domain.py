"""Dhan broker domain models.

Re-exports all canonical types from ``brokers.common.core.domain`` and
adds Dhan-specific types that have no broker-agnostic equivalent.

Usage::

    from brokers.dhan.domain import Order, Side, Exchange, Instrument
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

# ── Re-exports from canonical common domain ────────────────────────────────
# These are the single source of truth for order/trade/position/holding
# types and their associated enums across ALL broker adapters.

from brokers.common.core.domain import (  # noqa: F401  (re-exports)
    Balance,
    DepthLevel,
    FundLimits,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)

# ── IST helper ─────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

# ── Dhan-specific enums ────────────────────────────────────────────────────


class Exchange(str, Enum):
    """Dhan-supported exchange segments."""

    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"
    INDEX = "INDEX"


class InstrumentType(str, Enum):
    """Dhan instrument categories."""

    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    COMMODITY = "COMMODITY"


class OptionType(str, Enum):
    """Option flavour."""

    CALL = "CALL"
    PUT = "PUT"


# ── Dhan-specific dataclasses ──────────────────────────────────────────────


@dataclass(frozen=True)
class Instrument:
    """Full instrument definition as resolved by the Dhan symbol resolver."""

    symbol: str
    exchange: Exchange
    security_id: str
    instrument_type: InstrumentType
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    name: Optional[str] = None
    option_type: Optional[OptionType] = None
    strike_price: Optional[Decimal] = None
    expiry: Optional[str] = None
    underlying: Optional[str] = None
    canonical_symbol: Optional[str] = None

    @property
    def is_option(self) -> bool:
        return self.instrument_type == InstrumentType.OPTION

    @property
    def is_future(self) -> bool:
        return self.instrument_type == InstrumentType.FUTURE


# ── Backward-compatibility aliases ────────────────────────────────────────
# Existing code imports ``OrderSide`` — map it to the canonical ``Side``
# enum so that ``OrderSide.BUY`` / ``OrderSide.SELL`` keep working.

OrderSide = Side
