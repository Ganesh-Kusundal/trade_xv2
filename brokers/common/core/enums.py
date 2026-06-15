"""DEPRECATED: Use brokers.common.core.domain instead. Kept for Upstox compatibility.

Original description: Core broker enums — inspired by Trade_J domain model.
Each enum includes helper methods for common operations
(e.g. ``from_value``, ``opposite``, ``valid_for``, ``is_terminal``).

Canonical enums (Side, OrderStatus, ProductType, OrderType, Validity) live in
``brokers.common.core.domain``.  This module retains broker-specific enums that
have no domain.py equivalent (ExchangeSegment, FeedMode, InstrumentType,
TransactionType) plus legacy copies of the canonical enums needed by the Upstox
adapter and the Pydantic models in ``models.py``.
"""

from __future__ import annotations

from enum import Enum


class ExchangeSegment(str, Enum):
    """Exchange segments supported by the broker system."""

    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX = "MCX_COMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    IDX_I = "IDX_I"

    @classmethod
    def from_value(cls, value: str) -> ExchangeSegment:
        """Look up segment by string value, raising ValueError if not found."""
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown ExchangeSegment: {value}")

    def __str__(self) -> str:
        return self.value


class OrderType(str, Enum):
    """Order types."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


# Product segment map — defined at module level to avoid Enum metaclass issues
_PRODUCT_SEGMENT_MAP: dict = {
    "NSE_EQ": {"CNC", "INTRADAY", "MARGIN", "MTF"},
    "BSE_EQ": {"CNC", "INTRADAY", "MARGIN", "MTF"},
    "NSE_FNO": {"INTRADAY", "MARGIN"},
    "BSE_FNO": {"INTRADAY", "MARGIN"},
    "MCX_COMM": {"INTRADAY", "MARGIN"},
    "NSE_CURRENCY": {"INTRADAY", "MARGIN"},
}


class ProductType(str, Enum):
    """Product types for trades."""

    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"

    @classmethod
    def valid_for(cls, exchange_segment: str) -> set[ProductType]:
        """Return the product types valid for a given exchange segment."""
        raw = _PRODUCT_SEGMENT_MAP.get(exchange_segment, set())
        return {ProductType(name) for name in raw}  # type: ignore


class TransactionType(str, Enum):
    """Buy or Sell."""

    BUY = "BUY"
    SELL = "SELL"

    def opposite(self) -> TransactionType:
        """Return the opposite transaction type."""
        if self == TransactionType.BUY:
            return TransactionType.SELL
        return TransactionType.BUY


class OrderStatus(str, Enum):
    """Status of an order — includes terminal status helpers."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    TRIGGER_PENDING = "TRIGGER_PENDING"

    _TERMINAL_STATUSES = {EXECUTED, REJECTED, CANCELLED}

    def is_terminal(self) -> bool:
        """Check if this status is terminal (no further state changes possible)."""
        return self in self._TERMINAL_STATUSES


class Validity(str, Enum):
    """Order validity."""

    DAY = "DAY"
    IOC = "IOC"


class InstrumentType(str, Enum):
    """Instrument types."""

    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"
    INDEX = "INDEX"


class FeedMode(str, Enum):
    """WebSocket feed subscription mode.

    Maps to Trade_J's FeedMode: LTP, FULL, or DEPTH.
    """

    LTP = "LTP"
    FULL = "FULL"
    DEPTH = "DEPTH"
