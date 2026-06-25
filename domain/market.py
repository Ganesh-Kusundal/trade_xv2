"""Canonical market data dataclasses — quotes, depth, and instruments.

Submodule of :mod:`domain.entities` — imported via the re-export facade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from domain.constants import DEFAULT_TICK_SIZE
from domain.historical import InstrumentRef
from domain.provenance import DataProvenance


class DepthKind(str, Enum):
    """Describes the source and depth level of market depth data.

    REST_5   — 5-level depth from REST API (standard across all brokers).
    WS_20    — 20-level depth from WebSocket (Dhan-specific).
    WS_200   — 200-level depth from WebSocket (Dhan-specific, premium tier).
    """

    REST_5 = "REST_5"
    WS_20 = "WS_20"
    WS_200 = "WS_200"


@dataclass(slots=True, frozen=True)
class DepthLevel:
    """Single price level in market depth."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


@dataclass(slots=True, frozen=True)
class MarketDepth:
    """Canonical market depth — bid/ask ladder."""

    symbol: str = ""
    bids: list[DepthLevel] | None = None
    asks: list[DepthLevel] | None = None
    timestamp: datetime | None = None
    depth_kind: DepthKind = DepthKind.REST_5

    def __post_init__(self) -> None:
        # REF-027: Use object.__setattr__ for frozen dataclass compatibility.
        if self.bids is None:
            object.__setattr__(self, "bids", [])
        if self.asks is None:
            object.__setattr__(self, "asks", [])


@dataclass(slots=True, frozen=True)
class Quote:
    """Canonical quote snapshot — returned by every broker adapter."""

    symbol: str
    ltp: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
    timestamp: datetime | None = None


@dataclass(slots=True, frozen=True)
class Instrument:
    """Canonical instrument master record — returned by broker adapters.

    This is the broker-adapter-level instrument, populated by Dhan/Upstox
    instrument loaders. Distinct from:

    * ``brokers.common.core.instruments.Instrument`` — the trading-engine
      instrument used by the strategy layer (has ``asset_class``,
      ``broker_identifier``).
    * ``brokers.dhan.domain.Instrument`` — Dhan-specific instrument with
      typed ``Exchange`` and ``InstrumentType`` enums.
    """

    symbol: str
    exchange: str
    security_id: str
    instrument_type: str
    lot_size: int = 1
    tick_size: Decimal = DEFAULT_TICK_SIZE
    name: str | None = None
    option_type: str | None = None
    strike_price: Decimal | None = None
    expiry: str | None = None
    underlying: str | None = None
    canonical_symbol: str | None = None


@dataclass(slots=True, frozen=True)
class MarketTick:
    """Normalized market data tick — delivered by StreamOrchestrator to consumers.

    Every tick carries full provenance so consumers can trace data lineage.
    """

    instrument: InstrumentRef
    ltp: Decimal
    volume: int = 0
    bid: Decimal | None = None
    ask: Decimal | None = None
    event_time: datetime
    sequence: int | None = None
    provenance: DataProvenance
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


@dataclass(slots=True, frozen=True)
class QuoteSnapshot:
    """Point-in-time quote snapshot with provenance — returned by gateway methods.

    Distinct from ``Quote`` which is the older model without provenance.
    New code should prefer ``QuoteSnapshot`` for multi-broker auditing.
    """

    instrument: InstrumentRef
    ltp: Decimal
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change_pct: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
    event_time: datetime
    provenance: DataProvenance
