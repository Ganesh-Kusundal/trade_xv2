"""Broker-agnostic instrument loading / security-mapping port.

Every broker implements :class:`BrokerInstrumentService`. Gateways pass only
canonical ``(symbol, exchange)``; wire identifiers (Dhan ``security_id``,
Upstox ``instrument_key``) stay inside the broker connection.
"""

from __future__ import annotations

from brokers.common.instruments.carrier import BrokerWireRef, LoadStats, ResolvedInstrument
from brokers.common.instruments.keys import generate_alternate_keys
from brokers.common.instruments.service import BrokerInstrumentService

__all__ = [
    "BrokerInstrumentService",
    "BrokerWireRef",
    "LoadStats",
    "ResolvedInstrument",
    "generate_alternate_keys",
]
