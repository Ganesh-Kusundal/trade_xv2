"""Paper market data — seeded quotes only."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.entities import DepthLevel, MarketDepth, Quote
from domain.value_objects import InstrumentId, Price, TimeFrame

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperMarketDataAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection

    def get_quote(self, instrument_id: InstrumentId) -> Quote:
        quote = self._conn.quotes.get(instrument_id)
        if quote is None:
            raise KeyError(f"no quote seeded for {instrument_id.value}")
        return quote

    def get_ltp(self, instrument_id: InstrumentId) -> Price:
        quote = self.get_quote(instrument_id)
        return Price(value=(quote.bid.value + quote.ask.value) / Decimal("2"))

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth:
        quote = self.get_quote(instrument_id)
        return MarketDepth(
            instrument_id=instrument_id,
            bids=(DepthLevel(price=quote.bid, quantity=quote.bid_size),),
            asks=(DepthLevel(price=quote.ask, quantity=quote.ask_size),),
            timestamp=datetime.now(),
        )

    def get_history(
        self,
        instrument_id: InstrumentId,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime,
    ) -> list:
        return []
