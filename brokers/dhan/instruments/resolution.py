"""Dhan-internal resolved instrument wire bundle."""

from __future__ import annotations

from dataclasses import dataclass

from brokers.common.core.enums import ExchangeSegment
from brokers.dhan.mapper.instruments import DhanInstrumentDefinition


@dataclass(frozen=True)
class ResolvedInstrument:
    """Canonical result of symbol resolution for Dhan REST/WebSocket calls."""

    definition: DhanInstrumentDefinition
    security_id: str
    exchange_segment: ExchangeSegment
    wire_segment: str
    canonical_exchange: str
