"""Paper market data — seeded quotes only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.entities import Quote
from domain.value_objects import InstrumentId

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperMarketDataAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        self._conn.require_connected()
        quote = self._conn.quotes.get(instrument_id)
        if quote is None:
            raise KeyError(f"no quote seeded for {instrument_id.value}")
        return self._conn.wire.to_quote(quote)
