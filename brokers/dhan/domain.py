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

# ── Re-exports from canonical common domain ────────────────────────────────
# These are the single source of truth for order/trade/position/holding
# types and their associated enums across ALL broker adapters.
from brokers.common.core.domain import (
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
class MarginRequest:
    """Request shape for margin calculation."""

    symbol: str
    exchange: str
    quantity: int
    product_type: str
    order_type: str
    price: Decimal | None = None
    trigger_price: Decimal | None = None


@dataclass(frozen=True)
class MarginResponse:
    """Response from margin calculation API."""

    total_margin: Decimal
    order_margin: Decimal
    exposure_margin: Decimal
    available_margin: Decimal | None = None
    span_margin: Decimal | None = None


@dataclass(frozen=True)
class AlertRequest:
    """Request to create a price alert."""

    symbol: str
    exchange: str
    condition: str  # LTP_CROSSES_ABOVE, LTP_CROSSES_BELOW
    trigger_price: Decimal
    valid_until: str | None = None  # YYYY-MM-DD format


@dataclass(frozen=True)
class Alert:
    """Represents a created alert."""

    alert_id: str
    symbol: str
    exchange: str
    condition: str
    trigger_price: Decimal
    active: bool
    created_at: str | None = None


@dataclass(frozen=True)
class Instrument:
    """Full instrument definition as resolved by the Dhan symbol resolver."""

    symbol: str
    exchange: Exchange
    security_id: str
    instrument_type: InstrumentType
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    name: str | None = None
    option_type: OptionType | None = None
    strike_price: Decimal | None = None
    expiry: str | None = None
    underlying: str | None = None
    canonical_symbol: str | None = None
    sm_symbol_name: str | None = None

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
