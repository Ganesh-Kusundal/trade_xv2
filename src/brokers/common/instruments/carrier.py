"""Canonical and wire carriers for broker instrument resolution.

``ResolvedInstrument`` is what gateways / domain code may see.
``BrokerWireRef`` is opaque to the gateway — only the broker connection
consumes it when building HTTP / WebSocket payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class LoadStats:
    """Result of a broker instrument-master load."""

    total: int = 0
    skipped: int = 0
    skip_rate: float = 0.0
    source: str = "cached"

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "total": self.total,
            "skipped": self.skipped,
            "skip_rate": self.skip_rate,
            "source": self.source,
        }


@dataclass(frozen=True)
class ResolvedInstrument:
    """Canonical instrument record — no broker wire identifiers."""

    symbol: str
    exchange: str
    instrument_type: str = "EQUITY"
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    expiry: str | None = None
    strike: Decimal | None = None
    option_type: str | None = None
    underlying: str | None = None
    canonical_symbol: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class BrokerWireRef:
    """Opaque broker-native subscription / order identity.

    Subclasses (or broker-specific frozen dataclasses that duck-type this)
    carry the wire fields. Gateways must never read ``wire`` contents —
    only the connection / adapter that builds the broker payload may.
    """

    symbol: str
    exchange: str
    # Broker-native payload fragment. Shape is broker-defined:
    #   Dhan:  {"exchange_segment": "NSE_EQ", "security_id": "1333"}
    #   Upstox: {"instrument_key": "NSE_EQ|INE002A01018"}
    wire: dict[str, Any]

    def require(self, key: str) -> Any:
        if key not in self.wire:
            raise KeyError(f"BrokerWireRef missing wire key {key!r}")
        return self.wire[key]
