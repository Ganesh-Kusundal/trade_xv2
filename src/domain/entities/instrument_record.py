"""Instrument domain entity.

Renamed from ``Instrument`` to ``InstrumentRecord`` to clarify that this
is a broker-adapter-level data record (instrument master data), NOT the
rich domain object. Application code should use ``Instrument`` from
``domain.instruments.instrument`` as the canonical entry point.

Broker adapters continue to use ``InstrumentRecord`` internally for
instrument resolution and loading.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.constants import DEFAULT_TICK_SIZE


@dataclass(slots=True, frozen=True)
class InstrumentRecord:
    """Instrument master record — broker-adapter-level data record.

    This is the broker-adapter-level instrument, populated by Dhan/Upstox
    instrument loaders.  It carries static metadata about an instrument
    (symbol, exchange, security_id, lot_size, etc.) and is used internally
    by broker adapters for instrument resolution.

    Application code should use ``Instrument`` from ``domain.instruments.instrument``.
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


# Backward-compat alias — existing broker code imports Instrument, not InstrumentRecord.
# This alias will be removed once all broker adapters are migrated.
Instrument = InstrumentRecord
