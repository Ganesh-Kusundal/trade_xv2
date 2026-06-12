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

    @property
    def dhan_historical_instrument(self) -> str:
        """Dhan REST ``instrument`` payload value for historical endpoints."""
        defn = self.definition
        if defn.is_index:
            return "INDEX"
        if defn.is_future:
            return "FUTURES"
        if defn.is_option:
            return "OPTIONS"
        if defn.is_commodity:
            return "COMMODITY"
        if defn.is_currency:
            return "CURRENCY"
        return "EQUITY"
