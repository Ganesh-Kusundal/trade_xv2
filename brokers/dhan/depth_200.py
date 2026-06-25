"""200-level market depth WebSocket feed for Dhan.

Plan §7.1 refactor: the binary-packet / reconnect / lifecycle machinery is
shared with ``DhanDepth20Feed`` via :class:`BinaryDepthFeed` (in
``brokers.dhan.depth_feed_base``). This module keeps ``DhanDepth200Feed``
as a thin subclass so callers and tests that import
``brokers.dhan.depth_200.DhanDepth200Feed`` keep working unchanged.

Endpoint: wss://full-depth-api.dhan.co/twohundreddepth
Max instruments: 1 per connection (Dhan API limitation)
Header layout: num_rows at offset 8 (security_id is implicit per connection)
"""

from __future__ import annotations

import logging

from brokers.dhan.depth_feed_base import BinaryDepthFeed
from domain import MarketDepth
from infrastructure.event_bus import EventBus

__all__ = ["DhanDepth200Feed"]

logger = logging.getLogger(__name__)


class DhanDepth200Feed(BinaryDepthFeed):
    """200-level market depth via WebSocket.

    CRITICAL LIMITATION: Only 1 instrument per connection allowed. The
    security_id is implicit (carried in the subscription, not in the wire
    format); see ``BinaryDepthFeed.header_carries_security_id=False``.
    """

    name = "dhan.depth_200"
    MAX_INSTRUMENTS = 1
    TOTAL_DEPTH_PACKETS = 200
    REQUEST_CODE = 23
    HEADER_SIZE = 12
    DEPTH_LEVEL_SIZE = 16
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

    def __init__(
        self,
        client_id: str,
        access_token: str,
        instrument: tuple[str, str] | None = None,
        event_bus: EventBus | None = None,
    ):
        from endpoints import Dhan as _DhanEndpoints

        super().__init__(
            client_id=client_id,
            access_token=access_token,
            endpoint=_DhanEndpoints.WS_DEPTH_200,
            request_code=self.REQUEST_CODE,
            total_slots=200,
            subs_per_connection=1,
            depth_type="DEPTH_200",
            name=self.name,
            event_name="DEPTH_200",
            header_carries_security_id=False,
            event_bus=event_bus,
        )

        self._instrument = instrument
        if instrument:
            self.subscribe(instrument)

    # ── Depth-200: only one instrument ever, with a legacy error message ──
    def subscribe(self, instrument: tuple[str, str] | list[tuple[str, str]]) -> None:  # type: ignore[override]
        """Subscribe to a single instrument.

        Raises:
            ValueError: If already subscribed to an instrument (legacy
                error message ``"Only 1 instrument allowed for 200-level depth"``
                is preserved for backwards-compatible test assertions).
        """
        instruments = instrument if isinstance(instrument, list) else [instrument]

        # Legacy: depth-200 raises "Only 1 instrument allowed..." even when
        # the unified limit check would accept a single new instrument.
        [i for i in instruments if i in self._subscriptions]
        new_instruments = [i for i in instruments if i not in self._subscriptions]
        if not new_instruments:
            return
        if len(self._subscriptions) + len(new_instruments) > self.subs_per_connection:
            raise ValueError(
                f"Only {self.subs_per_connection} instrument allowed for "
                f"200-level depth. Already subscribed to "
                f"{self._subscriptions[0] if self._subscriptions else 'none'}"
            )

        self._subscriptions.extend(new_instruments)
        self._instrument = new_instruments[0]
        logger.info(
            "depth_200_subscribe",
            extra={"instrument": self._instrument},
        )

        if self._is_connected and self._ws:
            self._send_subscription(new_instruments)

    # ── Depth-200 specific lookup: single-instrument cache ─────────────────
    def latest_depth(self) -> MarketDepth | None:
        """Return the most-recent cached :class:`MarketDepth`."""
        with self._depth_cache_lock:
            if not self._depth_cache:
                return None
            entry = next(iter(self._depth_cache.values()))
            bids = list(entry.get("bids", []))
            asks = list(entry.get("asks", []))
        if not bids and not asks:
            return None
        return MarketDepth(bids=bids, asks=asks, depth_type="DEPTH_200")
