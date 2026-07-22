"""DataAdapter protocol — market data subscription and history."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from domain.entities import Bar, Instrument, Quote
from domain.value_objects import InstrumentId, TimeFrame, Timestamp


@runtime_checkable
class DataAdapter(Protocol):
    def subscribe(self, instrument: Instrument, timeframe: TimeFrame) -> None: ...
    def unsubscribe(self, instrument: Instrument) -> None: ...
    def request_history(
        self, instrument: Instrument, start: Timestamp, end: Timestamp
    ) -> Iterator[Bar]: ...
    def get_quote(self, instrument_id: InstrumentId) -> Quote: ...
