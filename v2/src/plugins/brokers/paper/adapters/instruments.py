"""Paper instruments — in-memory catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.entities import Instrument
from domain.value_objects import InstrumentId

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperInstrumentsAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection

    def load(self, instrument: Instrument) -> None:
        self._conn.instruments[instrument.instrument_id] = instrument

    def resolve(self, instrument_id: InstrumentId) -> Instrument:
        inst = self._conn.instruments.get(instrument_id)
        if inst is None:
            raise KeyError(f"unknown instrument {instrument_id.value}")
        return inst

    def search(self, query: str) -> list[Instrument]:
        q = query.upper()
        return [i for i in self._conn.instruments.values() if q in i.symbol.upper()]
