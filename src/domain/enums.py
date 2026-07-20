"""Canonical trading enums — the core vocabulary of the trading domain.

Submodule of :mod:`domain.types` — imported via the re-export facade.
"""

from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    """Order side — BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Canonical order status.

    Broker-specific variants (TRANSIT, TRIGGER PENDING, COMPLETE, etc.)
    must be normalized to these values at the adapter boundary.
    """

    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    PARTIALLY_CANCELLED = "PARTIALLY_CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def normalize(cls, raw: str) -> OrderStatus:
        """Normalize a broker-specific status string to canonical OrderStatus.

        Uses a lazy import of :class:`~domain.status_mapper.StatusMapperRegistry`
        to break the compile-time cycle: enums.py → status_mapper.py → enums.py.
        """
        from domain.status_mapper import StatusMapperRegistry

        return StatusMapperRegistry.normalize(raw)

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.PARTIALLY_CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }


class ProductType(str, Enum):
    """Canonical product types."""

    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"


class OrderType(str, Enum):
    """Canonical order types."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class Validity(str, Enum):
    """Order validity."""

    DAY = "DAY"
    IOC = "IOC"


class BrokerId(str, Enum):
    """Canonical broker identifier — replaces _active_name string branching.

    Architecture invariant #3: broker selected by enum, never string equality.
    Interface and runtime layers must compare against these values.
    """

    DHAN = "dhan"
    UPSTOX = "upstox"
    PAPER = "paper"
    DATALAKE = "datalake"

    @classmethod
    def from_str(cls, name: str) -> BrokerId:
        """Convert a string broker name to BrokerId (case-insensitive).

        ``mock`` maps to :attr:`PAPER` (duplicate MOCK member removed).
        """
        key = name.lower().strip()
        if key == "mock":
            return cls.PAPER
        try:
            return cls(key)
        except ValueError as exc:
            raise ValueError(
                f"Broker '{name}' is not registered. Use one of: {', '.join(b.value for b in cls)}"
            ) from exc
