"""Depth packet parser — binary packet parsing for Dhan depth feeds.

Extracted from :class:`~brokers.dhan.data.depth_feed_base.BinaryDepthFeed`
to keep the feed's connection/subscription machinery separate from wire-format
parsing logic.

Exports :class:`DepthPacketParser` which owns no state beyond the constants
it was configured with. All mutable state (caches, callbacks, counters) is
passed in at call time so the parser is safe to share or test in isolation.
"""

from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from domain import DepthLevel, MarketDepth
from domain.events import DomainEvent
from domain.symbols import normalize_symbol
from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)

# Header / level sizes — must match production Dhan binary layout.
HEADER_SIZE = 12
LEVEL_SIZE = 16  # 8 bytes price + 4 bytes quantity + 4 bytes orders


class DepthPacketParser:
    """Stateless binary-packet parser for Dhan depth-20/depth-200 streams.

    Parameters mirror the subset of ``BinaryDepthFeed`` class attributes
    that control wire-format interpretation (see Plan §7.1).
    """

    def __init__(
        self,
        total_slots: int,
        depth_type: str,
        header_carries_security_id: bool,
        bid_response_code: int = 41,
        ask_response_code: int = 51,
    ) -> None:
        self.total_slots = total_slots
        self.DEPTH_TYPE = depth_type
        self.header_carries_security_id = header_carries_security_id
        self.BID_RESPONSE_CODE = bid_response_code
        self.ASK_RESPONSE_CODE = ask_response_code

    # ── Packet processing ────────────────────────────────────────────────

    def parse_packet(self, data: bytes, header_value: int, response_code: int) -> dict:
        """Parse the depth body of a binary packet.

        For depth-20 *header_value* is the security_id (extracted from
        offset 4). For depth-200 *header_value* is the row count (offset 8);
        the security_id is implicit (one instrument per connection).
        """
        depth_levels: list[DepthLevel] = []
        for i in range(self.total_slots):
            offset = HEADER_SIZE + (i * LEVEL_SIZE)
            if offset + LEVEL_SIZE > len(data):
                break
            price = struct.unpack_from("<d", data, offset)[0]
            quantity = struct.unpack_from("<I", data, offset + 8)[0]
            orders = struct.unpack_from("<I", data, offset + 12)[0]
            if quantity > 0:
                depth_levels.append(
                    DepthLevel(
                        price=Decimal(str(round(price, 2))),
                        quantity=quantity,
                        orders=orders,
                    )
                )

        return {
            "levels": depth_levels,
            "side": "bids" if response_code == self.BID_RESPONSE_CODE else "asks",
            "header_value": header_value,
        }

    def process_binary_message(
        self,
        data: bytes,
        *,
        note_message_received: Any = None,
        subscriptions: list[tuple[str, str]] | None = None,
        depth_cache: dict[int, dict[str, list[DepthLevel]]] | None = None,
        depth_cache_lock: Any | None = None,
        sec_id_to_symbol: dict[int, str] | None = None,
        depth_callbacks: list[Any] | None = None,
        callback_lock: Any | None = None,
        event_bus: EventBus | None = None,
        event_name: str = "",
        feed_name: str = "",
        snapshot_callbacks: Any = None,
        next_correlation_id: Any = None,
        counters: dict[str, int] | None = None,
    ) -> None:
        """Parse a binary depth packet, update caches, and dispatch callbacks.

        Accepts all mutable feed state as explicit parameters so the parser
        remains stateless and testable without a ``BinaryDepthFeed`` instance.
        """
        if counters is None:
            counters = {}

        try:
            if len(data) < HEADER_SIZE:
                logger.warning(
                    "%s_packet_too_short: %d bytes",
                    self.DEPTH_TYPE.lower(),
                    len(data),
                )
                return

            response_code = data[2]

            if self.header_carries_security_id:
                # depth-20 layout: offset 4 = security_id
                header_value = struct.unpack_from("<I", data, 4)[0]
            else:
                # depth-200 layout: offset 8 = num_rows
                header_value = struct.unpack_from("<I", data, 8)[0]

            # Notify the caller that a message was received (for health tracking).
            if callable(note_message_received):
                note_message_received()

            if response_code in (self.BID_RESPONSE_CODE, self.ASK_RESPONSE_CODE):
                depth_data = self.parse_packet(data, header_value, response_code)
                self._dispatch_depth(
                    depth_data,
                    subscriptions=subscriptions or [],
                    depth_cache=depth_cache or {},
                    depth_cache_lock=depth_cache_lock,
                    sec_id_to_symbol=sec_id_to_symbol or {},
                    depth_callbacks=depth_callbacks or [],
                    callback_lock=callback_lock,
                    event_bus=event_bus,
                    event_name=event_name,
                    feed_name=feed_name,
                    snapshot_callbacks=snapshot_callbacks,
                    next_correlation_id=next_correlation_id,
                    counters=counters,
                )

        except Exception as exc:
            logger.exception("%s_parse_error: %s", self.DEPTH_TYPE.lower(), exc)

    # ── Dispatch ─────────────────────────────────────────────────────────

    def _dispatch_depth(
        self,
        depth_data: dict,
        *,
        subscriptions: list[tuple[str, str]],
        depth_cache: dict[int, dict[str, list[DepthLevel]]],
        depth_cache_lock: Any,
        sec_id_to_symbol: dict[int, str],
        depth_callbacks: list[Any],
        callback_lock: Any,
        event_bus: EventBus | None,
        event_name: str,
        feed_name: str,
        snapshot_callbacks: Any,
        next_correlation_id: Any,
        counters: dict[str, int],
    ) -> None:
        """Update the depth cache and dispatch to callbacks / event bus."""
        side = depth_data["side"]
        levels = depth_data["levels"]

        if self.header_carries_security_id:
            sec_id = depth_data["header_value"]
        else:
            sec_id = self._resolve_implicit_security_id(subscriptions, depth_cache)
        if sec_id is None:
            counters["dropped_depths"] = counters.get("dropped_depths", 0) + 1
            logger.warning(
                "%s_packet_dropped_no_security_id: arriving before subscribe()",
                self.DEPTH_TYPE.lower(),
            )
            return

        symbol = sec_id_to_symbol.get(sec_id, "")

        # Update cache under lock.
        if depth_cache_lock is not None:
            depth_cache_lock.acquire()
        try:
            entry = depth_cache.setdefault(sec_id, {"bids": [], "asks": []})
            if levels:
                entry[side] = levels
            merged = MarketDepth(
                symbol=symbol,
                bids=list(entry["bids"]),
                asks=list(entry["asks"]),
                depth_type=self.DEPTH_TYPE,
                timestamp=datetime.now(timezone.utc),
            )
        finally:
            if depth_cache_lock is not None:
                depth_cache_lock.release()

        # Local callbacks.
        cbs = list(depth_callbacks) if callback_lock is None else snapshot_callbacks(depth_callbacks)
        for cb in cbs:
            try:
                cb(merged)
            except Exception as exc:
                logger.error("%s_callback_error: %s", self.DEPTH_TYPE.lower(), exc)

        # Event-bus publish.
        if event_bus is not None:
            try:
                corr_id = next_correlation_id(prefix=f"depth_{self.DEPTH_TYPE.lower()}")
                event_bus.publish(
                    DomainEvent.now(
                        event_name,
                        {
                            "depth": merged,
                            "depth_type": self.DEPTH_TYPE,
                            "correlation_id": corr_id,
                        },
                        symbol=symbol or None,
                        source=feed_name,
                        correlation_id=corr_id,
                    )
                )
                counters["published_depths"] = counters.get("published_depths", 0) + 1
            except Exception as exc:
                counters["dropped_depths"] = counters.get("dropped_depths", 0) + 1
                logger.error("%s_event_publish_error: %s", self.DEPTH_TYPE.lower(), exc)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def resolve_implicit_security_id(
        subscriptions: list[tuple[str, str]],
        depth_cache: dict[int, Any],
    ) -> int | None:
        """Recover security_id for depth-200 (single instrument per connection).

        Returns ``None`` if no instrument is subscribed and cache is empty.
        """
        if subscriptions:
            try:
                return int(subscriptions[0][1])
            except (ValueError, IndexError):
                pass
        if depth_cache:
            return next(iter(depth_cache))
        return None
