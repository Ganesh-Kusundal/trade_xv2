"""Map canonical InstrumentId to broker-specific symbols."""

from __future__ import annotations

from domain.value_objects import InstrumentId


class SymbolNotFoundError(KeyError):
    pass


class SymbolResolver:
    def __init__(self) -> None:
        self._to_symbol: dict[InstrumentId, str] = {}
        self._to_instrument: dict[str, InstrumentId] = {}

    def add(self, instrument_id: InstrumentId, symbol: str) -> None:
        self._to_symbol[instrument_id] = symbol
        self._to_instrument[symbol] = instrument_id

    def resolve(self, instrument_id: InstrumentId) -> str:
        try:
            return self._to_symbol[instrument_id]
        except KeyError as exc:
            raise SymbolNotFoundError(f"{instrument_id} not resolved") from exc

    def lookup(self, symbol: str) -> InstrumentId:
        try:
            return self._to_instrument[symbol]
        except KeyError as exc:
            raise SymbolNotFoundError(f"symbol {symbol!r} not resolved") from exc
