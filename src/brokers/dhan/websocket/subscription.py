"""MarketFeedSubscriptionManager — subscription state and callback management.

Extracted from the former ``DhanMarketFeed`` class in ``market_feed.py``
as part of the subscription-logic modularization (Task 2).  Owns the
instrument subscription set, callback lists, tick-tracking state, and
sequence counter logic.

The parent ``DhanMarketFeed`` creates one instance and delegates all
subscribe/unsubscribe/callback registration calls to it.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from brokers.dhan.websocket._helpers import _to_sdk_instruments
from domain.ports.time_service import get_current_clock

logger = logging.getLogger(__name__)


class MarketFeedSubscriptionManager:
    """Manages instrument subscriptions, callbacks, and tick-tracking state.

    Thread safety is provided by the parent's ``_lock`` (an ``RLock``)
    which is shared across ``MarketFeedSubscriptionManager``, the parent
    ``DhanMarketFeed``, and ``MarketFeedConnection`` so that state
    invariants that span multiple components remain atomic.
    """

    MAX_INSTRUMENTS = 1000  # Dhan WebSocket limit per connection

    def __init__(
        self,
        *,
        instruments: list[tuple],
        lock: threading.RLock,
        feed_ref: Any = None,
    ) -> None:
        """Initialise the subscription manager.

        Args:
            instruments: Initial list of ``(exchange, security_id, mode)`` tuples.
            lock: Shared ``RLock`` from the parent ``DhanMarketFeed``.
            feed_ref: Optional backreference to the parent (for feed access).
        """
        self._feed_ref = feed_ref
        self._lock = lock
        self._raw_instruments = list(instruments)
        self._instruments: list[tuple] = list(_to_sdk_instruments(instruments))
        # _subscribed_instruments is the single source of truth for what
        # instruments should be active on the WebSocket at all times.
        # On reconnect, the full set is replayed — no separate pending queue needed.
        self._subscribed_instruments: set[tuple] = set(self._instruments)

        # Callback lists.
        self._quote_callbacks: list[Callable[[dict], None]] = []
        self._depth_callbacks: list[Callable[[dict], None]] = []

        # Tick tracking for gap detection (reconnect backfill).
        self._last_tick_time: dict[str, datetime] = {}

        # Synthetic per-instrument sequence counters.
        self._sequence_counters: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, instruments: list[tuple]) -> None:
        """Add instruments to the subscription.

        Deduplicates instruments — instruments already subscribed are ignored.

        Raises:
            ValueError: If total subscriptions would exceed MAX_INSTRUMENTS.
        """
        with self._lock:
            sdk_instruments = _to_sdk_instruments(instruments)
            new_instruments = [i for i in sdk_instruments if i not in self._subscribed_instruments]
            if not new_instruments:
                logger.debug("subscribe: no new instruments (already subscribed)")
                return
            total = len(self._subscribed_instruments) + len(new_instruments)
            if total > self.MAX_INSTRUMENTS:
                raise ValueError(
                    f"Dhan WebSocket limit is {self.MAX_INSTRUMENTS} instruments, "
                    f"would have {total}. Unsubscribe some first."
                )
            self._instruments.extend(new_instruments)
            self._subscribed_instruments.update(new_instruments)
            logger.info("subscribe: adding %d instruments (total=%d)", len(new_instruments), total)

            feed = self._feed_ref._conn.feed if self._feed_ref is not None else None
            is_connected = self._feed_ref._conn.is_connected if self._feed_ref is not None else False

            if feed and is_connected:
                logger.info(
                    "subscribe: calling SDK subscribe_symbols with %d instruments",
                    len(new_instruments),
                )
                try:
                    feed.subscribe_symbols(new_instruments)
                except Exception as exc:
                    self._feed_ref._conn._is_connected = False
                    self._feed_ref._conn._disconnect_time = get_current_clock().now()
                    logger.error("subscribe: SDK subscribe_symbols failed: %s", exc)
                    with contextlib.suppress(Exception):
                        feed.close_connection()
            else:
                logger.info(
                    "subscribe: feed not connected — %d instruments queued for reconnect",
                    len(new_instruments),
                )
            # Warn when approaching instrument limit (80% threshold)
            if total > self.MAX_INSTRUMENTS * 0.8:
                logger.warning(
                    "dhan_ws_instrument_limit_approaching",
                    extra={"current": total, "max": self.MAX_INSTRUMENTS},
                )

    def unsubscribe(self, instruments: list[tuple]) -> None:
        """Remove instruments from the subscription."""
        with self._lock:
            sdk_instruments = _to_sdk_instruments(instruments)
            feed = self._feed_ref._conn.feed if self._feed_ref is not None else None
            is_connected = self._feed_ref._conn.is_connected if self._feed_ref is not None else False
            if feed and is_connected:
                try:
                    feed.unsubscribe_symbols(sdk_instruments)
                except Exception as exc:
                    logger.warning("unsubscribe: SDK unsubscribe_symbols failed: %s", exc)
            for inst in sdk_instruments:
                self._subscribed_instruments.discard(inst)
                with contextlib.suppress(ValueError):
                    self._instruments.remove(inst)
            logger.info(
                "unsubscribe: removed %d instruments (remaining=%d)",
                len(sdk_instruments),
                len(self._subscribed_instruments),
            )

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_quote(self, callback: Callable[[dict], None]) -> None:
        """Register callback for quote updates."""
        if self._feed_ref is not None:
            self._feed_ref._register_callback(self._quote_callbacks, callback)

    def on_depth(self, callback: Callable[[dict], None]) -> None:
        """Register callback for depth updates."""
        if self._feed_ref is not None:
            self._feed_ref._register_callback(self._depth_callbacks, callback)

    def off_quote(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered quote callback."""
        if self._feed_ref is not None:
            self._feed_ref._unregister_callback(self._quote_callbacks, callback)
        else:
            with self._lock, contextlib.suppress(ValueError):
                self._quote_callbacks.remove(callback)

    def off_depth(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered depth callback."""
        if self._feed_ref is not None:
            self._feed_ref._unregister_callback(self._depth_callbacks, callback)
        else:
            with self._lock, contextlib.suppress(ValueError):
                self._depth_callbacks.remove(callback)

    def snapshot_quote_callbacks(self) -> list[Callable[[dict], None]]:
        """Return a snapshot of quote callbacks for safe iteration."""
        if self._feed_ref is not None:
            return self._feed_ref._snapshot_callbacks(self._quote_callbacks)
        with self._lock:
            return list(self._quote_callbacks)

    def snapshot_depth_callbacks(self) -> list[Callable[[dict], None]]:
        """Return a snapshot of depth callbacks for safe iteration."""
        if self._feed_ref is not None:
            return self._feed_ref._snapshot_callbacks(self._depth_callbacks)
        with self._lock:
            return list(self._depth_callbacks)

    # ------------------------------------------------------------------
    # Tick tracking
    # ------------------------------------------------------------------

    def track_tick_time(self, quote: dict) -> None:
        """Record the latest tick time per symbol for gap detection."""
        symbol = quote.get("symbol")
        if not symbol:
            return
        now = get_current_clock().now()
        with self._lock:
            prev = self._last_tick_time.get(symbol)
            if prev is None or now > prev:
                self._last_tick_time[symbol] = now

    def clear_symbol_tracking(self, symbol: str) -> None:
        """Remove last-tick-time tracking for a symbol (called on unsubscribe)."""
        with self._lock:
            self._last_tick_time.pop(symbol.upper(), None)
            self._last_tick_time.pop(symbol, None)

    def cleanup_stale_tick_tracking(self, max_age_seconds: float = 1800) -> None:
        """Remove entries for symbols that haven't received ticks recently.

        Default max_age is 30 minutes — conservative to avoid removing
        symbols that are still active but receive infrequent ticks.
        """
        now = get_current_clock().now()
        with self._lock:
            stale = [
                sym
                for sym, ts in self._last_tick_time.items()
                if (now - ts).total_seconds() > max_age_seconds
            ]
            for sym in stale:
                del self._last_tick_time[sym]

    # ------------------------------------------------------------------
    # Per-instrument sequence counters
    # ------------------------------------------------------------------

    def next_sequence(self, symbol: str) -> int:
        """Increment and return the monotonic sequence counter for *symbol*."""
        seq = self._sequence_counters.get(symbol, 0) + 1
        self._sequence_counters[symbol] = seq
        return seq

    def symbol_tick_times(self) -> dict[str, datetime]:
        """Return a snapshot of the last tick time per symbol."""
        with self._lock:
            return dict(self._last_tick_time)

    # ------------------------------------------------------------------
    # Correlation ID generation
    # ------------------------------------------------------------------

    @staticmethod
    def gen_ws_correlation_id() -> str:
        """Generate a traceable correlation_id for websocket message dispatch."""
        import uuid as _uuid

        return f"dhan:ws:{_uuid.uuid4().hex[:12]}"

    # ------------------------------------------------------------------
    # Test support
    # ------------------------------------------------------------------

    @property
    def subscribed_instruments(self) -> set:
        return self._subscribed_instruments
