"""Dhan broker domain models.

Re-exports all canonical types from ``brokers.common.core.domain`` and
adds Dhan-specific types that have no broker-agnostic equivalent.

Usage::

    from brokers.dhan.domain import Order, Side, Exchange, Instrument
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

# ── Re-exports from canonical common domain ────────────────────────────────
# These are the single source of truth for order/trade/position/holding
# types and their associated enums across ALL broker adapters.

from brokers.common.core.domain import (  # noqa: F401  (re-exports)
    FundLimits,
    Holding,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
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


@dataclass(frozen=True)
class Quote:
    """Real-time quote — Dhan uses the ``ltp`` naming convention."""

    symbol: str
    ltp: Decimal
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(IST))


@dataclass(frozen=True)
class DepthLevel:
    """Single price level in the market depth."""

    price: Decimal
    quantity: int
    orders: int = 0


@dataclass(frozen=True)
class MarketDepth:
    """Full market depth (bid/ask ladder) for a symbol."""

    symbol: str
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(IST))


@dataclass(frozen=True)
class Balance:
    """Dhan-specific fund limits — extends canonical Balance with Dhan-specific fields.

    IS-A relationship: Dhan Balance is a common Balance with additional fields.
    """

    available_balance: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    utilized_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")


# ── Backward-compatibility aliases ────────────────────────────────────────
# Existing code imports ``OrderSide`` — map it to the canonical ``Side``
# enum so that ``OrderSide.BUY`` / ``OrderSide.SELL`` keep working.

OrderSide = Side
