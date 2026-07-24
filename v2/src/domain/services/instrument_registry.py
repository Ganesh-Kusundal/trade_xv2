"""InstrumentRegistry — central registry mapping symbols to instruments."""

from __future__ import annotations

from domain.entities import Instrument
from domain.enums import ExchangeId


class InstrumentRegistry:
    """Maps symbol strings to Instrument objects. Owned by broker plugin + data catalog."""

    def __init__(self) -> None:
        self._by_symbol: dict[str, Instrument] = {}

    def register(self, instrument: Instrument) -> None:
        self._by_symbol[instrument.symbol] = instrument

    def lookup(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol)

    def instruments_by_exchange(self, exchange: ExchangeId) -> list[Instrument]:
        return [i for i in self._by_symbol.values() if i.exchange == exchange]
