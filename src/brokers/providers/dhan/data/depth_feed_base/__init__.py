"""Unified binary-packet depth WebSocket feed for Dhan.

Plan §7.1: ``DhanDepth20Feed`` (50 instruments, depth-20 layout) and
``DhanDepth200Feed`` (1 instrument, depth-200 layout) used to duplicate
the binary-packet framing, header parsing, level loop, quantity filter,
side cache, reconnect loop, callback fan-out, and event-bus emission.
The only meaningful differences were:

- ``MAX_INSTRUMENTS``         (50 vs 1)
- ``TOTAL_DEPTH_PACKETS``     (20 vs 200)
- ``ENDPOINT``                (WS_DEPTH_20 vs WS_DEPTH_200)
- ``REQUEST_CODE``            (23 vs 23 — same)
- ``DEPTH_TYPE``              ("DEPTH_20" vs "DEPTH_200")
- Header layout in the binary packet itself (``security_id`` at offset 4
  for depth-20, ``num_rows`` at offset 8 for depth-200) — see Plan §5.1.

This module introduces :class:`BinaryDepthFeed` that owns the shared
machinery, plus thin subclasses ``DhanDepth20Feed`` and
``DhanDepth200Feed`` that preserve the exact public surface their callers
and tests already use.

Re-exports from sub-modules maintain backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

from brokers.providers.dhan.market_data.depth_feed_base.connection import ConnectionMixin
from brokers.providers.dhan.streaming.connection_admission import MarketFeedConnectionAdmission
from brokers.providers.dhan.api.reconnecting_service import ReconnectingServiceMixin
from brokers.providers.dhan.market_data.depth_parser import DepthPacketParser
from domain.entities import DepthLevel, MarketDepth
from domain.symbols import normalize_symbol
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.lifecycle.lifecycle import ManagedService

logger = logging.getLogger(__name__)


# Header / level sizes — must match production Dhan binary layout.
_HEADER_SIZE = 12
_LEVEL_SIZE = 16  # 8 bytes price + 4 bytes quantity + 4 bytes orders


class BinaryDepthFeed(ConnectionMixin, ReconnectingServiceMixin, ManagedService):
    """Unified WebSocket feed for Dhan's binary depth streams.

    Parameters
    ----------
    total_slots:
        Number of depth levels per side that the wire format carries
        (20 for ``DhanDepth20Feed``, 200 for ``DhanDepth200Feed``).
    subs_per_connection:
        Hard cap on the number of (segment, security_id) tuples one
        connection may subscribe to (50 for depth-20, 1 for depth-200).
    endpoint, request_code, depth_type:
        Wire-format identifiers stamped on every message.
    header_carries_security_id:
        ``True`` for depth-20 (offset 4 = security_id); ``False`` for
        depth-200 (offset 8 = num_rows, security_id is implicit per
        connection). See Plan §5.1 for the layout divergence.
    name:
        ManagedService identifier — ``"dhan.depth_20"`` / ``"dhan.depth_200"``.
    event_name:
        EventBus event name — ``"DEPTH_20"`` / ``"DEPTH_200"``.
    """

    total_slots: int
    subs_per_connection: int
    ENDPOINT: str
    REQUEST_CODE: int
    DEPTH_TYPE: str
    name: str
    EVENT_NAME: str
    header_carries_security_id: bool

    # Binary packet constants (also exposed as class attrs for backwards compat)
    HEADER_SIZE = _HEADER_SIZE
    DEPTH_LEVEL_SIZE = _LEVEL_SIZE
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

    def __init__(
        self,
        client_id: str,
        access_token: str,
        endpoint: str,
        request_code: int,
        total_slots: int,
        subs_per_connection: int,
        depth_type: str,
        name: str,
        event_name: str,
        header_carries_security_id: bool,
        event_bus: EventBus | None = None,
        admission: Any | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token
        self._event_bus = event_bus
        # Shared 429-cooldown tracking per (client_id, depth_type). Unlike
        # market-feed, depth-200 intentionally opens multiple concurrent
        # connections (one per instrument via Depth200ConnectionPool), so we
        # only reuse the cooldown bookkeeping here, never try_acquire/release
        # — the exclusive host lock is not appropriate for a connection type
        # that legitimately runs several connections at once.
        self._admission = admission or MarketFeedConnectionAdmission(
            client_id, connection_type=f"depth-{depth_type.lower()}"
        )

        self.ENDPOINT = endpoint
        self.REQUEST_CODE = request_code
        self.total_slots = total_slots
        self.subs_per_connection = subs_per_connection
        self.DEPTH_TYPE = depth_type
        self.name = name
        self.EVENT_NAME = event_name
        self.header_carries_security_id = header_carries_security_id

        # Public aliases preserved on the class so legacy code/tests reading
        # ``DhanDepth20Feed.MAX_INSTRUMENTS`` etc. still resolve.
        self.MAX_INSTRUMENTS = subs_per_connection
        self.TOTAL_DEPTH_PACKETS = total_slots

        self._subscriptions: list[tuple[str, str]] = []
        # Backwards-compat alias for code/tests reading ``_instruments``.
        self._instruments: list[tuple[str, str]] = self._subscriptions
        self._depth_callbacks: list[Callable[[MarketDepth], None]] = []
        self._callback_lock = threading.Lock()

        self._ws = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        # Plan §7.2: shared reconnect / message-tracking state from the
        # ReconnectingServiceMixin. The mixin replaces the duplicated
        # ``_stop_event``/``_is_connected``/``_reconnect_count``/``_last_message_at``
        # attributes that previously lived on every depth feed.
        self._init_reconnect_state()
        self._lock = threading.Lock()

        # Per-security_id depth cache.  Each entry holds the last-seen bids
        # and asks independently so that a one-sided packet never zeros out
        # the other side. For depth-200 (1 instrument per connection) there
        # is exactly one entry; the dict-keyed shape is future-proof against
        # gateway-level fan-out.
        self._depth_cache: dict[int, dict[str, list[DepthLevel]]] = {}
        self._depth_cache_lock = threading.Lock()
        # security_id → canonical symbol for EventBus routing and MarketDepth.symbol
        self._sec_id_to_symbol: dict[int, str] = {}
        # Counters surfaced via health() so an operator can see
        # drop+publish rates without scraping logs.
        self._published_depths = 0
        self._dropped_depths = 0

        # Depth-packet parser — stateless wire-format decoder extracted from
        # this class so parsing can be tested in isolation.
        self._parser = DepthPacketParser(
            total_slots=total_slots,
            depth_type=depth_type,
            header_carries_security_id=header_carries_security_id,
            bid_response_code=self.BID_RESPONSE_CODE,
            ask_response_code=self.ASK_RESPONSE_CODE,
        )

    # ── Subscription management ────────────────────────────────────────────

    @property
    def max_instruments(self) -> int:
        """Maximum number of instruments allowed per connection."""
        return self.subs_per_connection

    @property
    def subscriptions(self) -> list[tuple[str, str]]:
        """Return a copy of the current subscription list."""
        return list(self._subscriptions)

    @property
    def is_running(self) -> bool:
        """Whether the feed thread is alive (started and not stopped)."""
        return bool(self._thread and self._thread.is_alive())

    def on_depth(self, callback: Callable[[MarketDepth], None]) -> None:
        """Register a callback for depth updates."""
        with self._callback_lock:
            self._depth_callbacks.append(callback)

    def off_depth(self, callback: Callable[[MarketDepth], None]) -> None:
        """Remove a previously registered depth callback."""
        self._unregister_callback(self._depth_callbacks, callback)

    def off_quote(self, callback: Callable[[MarketDepth], None]) -> None:
        """Remove a depth-feed callback via the ``off_quote`` alias."""
        self._unregister_callback(self._depth_callbacks, callback)

    def register_symbol(self, security_id: int, symbol: str) -> None:
        """Map a Dhan security_id to a canonical symbol for event routing."""
        self._sec_id_to_symbol[int(security_id)] = normalize_symbol(symbol)

    def subscribe(self, instruments: list[tuple[str, str]] | tuple[str, str]) -> None:
        """Subscribe to one or more instruments."""
        new_instruments = [instruments] if isinstance(instruments, tuple) else list(instruments)

        new_instruments = [i for i in new_instruments if i not in self._subscriptions]
        if not new_instruments:
            return
        total = len(self._subscriptions) + len(new_instruments)
        if total > self.subs_per_connection:
            raise ValueError(
                f"Maximum {self.subs_per_connection} instrument"
                f"{'s' if self.subs_per_connection != 1 else ''} allowed for "
                f"{self.DEPTH_TYPE} depth, would have {total}"
            )

        self._subscriptions.extend(new_instruments)
        logger.info(
            "%s_subscribe",
            self.DEPTH_TYPE.lower(),
            extra={"count": len(new_instruments), "total": len(self._subscriptions)},
        )

        if self._is_connected and self._ws:
            self._send_subscription(new_instruments)

    def unsubscribe(
        self, instruments: list[tuple[str, str]] | tuple[str, str] | None = None
    ) -> None:
        """Unsubscribe from instruments and evict their depth cache entries."""
        if instruments is None:
            removed = list(self._subscriptions)
            self._subscriptions.clear()
            with self._depth_cache_lock:
                self._depth_cache.clear()
            logger.info("%s_unsubscribe_all", self.DEPTH_TYPE.lower())
            return

        instruments_list = [instruments] if isinstance(instruments, tuple) else list(instruments)

        removed: list[tuple[str, str]] = []
        for inst in instruments_list:
            if inst in self._subscriptions:
                self._subscriptions.remove(inst)
                removed.append(inst)
                try:
                    sec_id = int(inst[1])
                    with self._depth_cache_lock:
                        self._depth_cache.pop(sec_id, None)
                except (ValueError, IndexError):
                    pass

        if removed:
            logger.info(
                "%s_unsubscribe",
                self.DEPTH_TYPE.lower(),
                extra={"count": len(removed), "total": len(self._subscriptions)},
            )

    # ── Backwards-compatibility helpers ─────────────────────────────────────

    def _parse_depth_packet(self, data: bytes, response_code: int, header_value: int) -> dict:
        """Backwards compatibility helper for tests."""
        return self._parser.parse_packet(data, header_value, response_code)

    def _process_binary_message(self, data: bytes) -> None:
        """Backwards compatibility helper for tests."""
        counters = {"published_depths": 0, "dropped_depths": 0}
        self._parser.process_binary_message(
            data,
            note_message_received=self._note_message_received,
            subscriptions=self._subscriptions,
            depth_cache=self._depth_cache,
            depth_cache_lock=self._depth_cache_lock,
            sec_id_to_symbol=self._sec_id_to_symbol,
            depth_callbacks=self._depth_callbacks,
            callback_lock=self._callback_lock,
            event_bus=self._event_bus,
            event_name=self.EVENT_NAME,
            feed_name=self.name,
            snapshot_callbacks=self._snapshot_callbacks,
            next_correlation_id=self.next_correlation_id,
            counters=counters,
        )
        self._published_depths += counters["published_depths"]
        self._dropped_depths += counters["dropped_depths"]

    def _dispatch_depth(self, depth_data: dict) -> None:
        """Backwards compatibility helper for tests."""
        if "header_value" not in depth_data:
            if not self.header_carries_security_id and self._subscriptions:
                try:
                    depth_data["header_value"] = int(self._subscriptions[0][1])
                except (ValueError, IndexError):
                    depth_data["header_value"] = 0
            else:
                depth_data["header_value"] = 0

        counters = {"published_depths": 0, "dropped_depths": 0}
        self._parser._dispatch_depth(
            depth_data,
            subscriptions=self._subscriptions,
            depth_cache=self._depth_cache,
            depth_cache_lock=self._depth_cache_lock,
            sec_id_to_symbol=self._sec_id_to_symbol,
            depth_callbacks=self._depth_callbacks,
            callback_lock=self._callback_lock,
            event_bus=self._event_bus,
            event_name=self.EVENT_NAME,
            feed_name=self.name,
            snapshot_callbacks=self._snapshot_callbacks,
            next_correlation_id=self.next_correlation_id,
            counters=counters,
        )
        self._published_depths += counters["published_depths"]
        self._dropped_depths += counters["dropped_depths"]


__all__ = [
    "BinaryDepthFeed",
]
