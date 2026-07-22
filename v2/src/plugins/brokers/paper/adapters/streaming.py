"""Paper streaming — subscribe list only (no push)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.value_objects import InstrumentId

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection


class PaperStreamingAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection
        self.subscriptions: list[InstrumentId] = []

    def subscribe(self, instrument_id: InstrumentId) -> None:
        if instrument_id not in self.subscriptions:
            self.subscriptions.append(instrument_id)

    def unsubscribe(self, instrument_id: InstrumentId) -> None:
        self.subscriptions = [s for s in self.subscriptions if s != instrument_id]
