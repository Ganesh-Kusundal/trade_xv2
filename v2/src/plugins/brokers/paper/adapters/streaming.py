"""Paper streaming — in-memory callback-based quote/order push."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from domain.value_objects import InstrumentId

if TYPE_CHECKING:
    from plugins.brokers.paper.connection import PaperConnection

Callback = Callable[..., None]


class PaperStreamingAdapter:
    def __init__(self, connection: PaperConnection) -> None:
        self._conn = connection
        self.subscriptions: list[InstrumentId] = []
        self._quote_callbacks: dict[InstrumentId, list[Callback]] = {}
        self._order_callbacks: list[Callback] = []

    # -- subscription management ------------------------------------------------

    def subscribe(self, instrument_id: InstrumentId) -> None:
        if instrument_id not in self.subscriptions:
            self.subscriptions.append(instrument_id)

    def unsubscribe(self, instrument_id: InstrumentId) -> None:
        self.subscriptions = [s for s in self.subscriptions if s != instrument_id]

    # -- streaming (callback registration) --------------------------------------

    def stream(self, instrument_id: InstrumentId, callback: Callback) -> None:
        """Register *callback* for quote updates on *instrument_id*."""
        if instrument_id not in self._quote_callbacks:
            self._quote_callbacks[instrument_id] = []
        self._quote_callbacks[instrument_id].append(callback)

    def unstream(self, instrument_id: InstrumentId) -> None:
        """Unregister all callbacks for *instrument_id*."""
        self._quote_callbacks.pop(instrument_id, None)

    def stream_order(self, callback: Callback) -> None:
        """Register *callback* for order status updates."""
        self._order_callbacks.append(callback)

    # -- feed (for testing) -----------------------------------------------------

    def feed_raw(self, instrument_id: InstrumentId, quote: object) -> None:
        """Push *quote* to every callback registered on *instrument_id*."""
        for cb in self._quote_callbacks.get(instrument_id, []):
            cb(instrument_id, quote)

    # -- lifecycle --------------------------------------------------------------

    def close(self) -> None:
        """Clear all subscriptions and callbacks."""
        self.subscriptions.clear()
        self._quote_callbacks.clear()
        self._order_callbacks.clear()
