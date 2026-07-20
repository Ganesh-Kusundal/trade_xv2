"""DhanMarketFeed — real-time market data via Dhan SDK WebSocket.

Extracted connection lifecycle to :class:`MarketFeedConnection` and
subscription management to :class:`MarketFeedSubscriptionManager`
(Task 2).  Pure payload parsing lives in ``_helpers``.  This module is a
thin facade that composes both managers and owns the message
transformation / publishing pipeline.

All existing import paths continue to work:

    from brokers.dhan.websocket import DhanMarketFeed
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from brokers.dhan.api.reconnecting_service import ReconnectingServiceMixin
from brokers.dhan.streaming.connection_admission import MarketFeedConnectionAdmission
from brokers.dhan.websocket._helpers import (
    _DhanContext,
    _normalize_sdk_depth,
    _to_decimal,
    _transform_depth,
    _transform_quote,
)
from brokers.dhan.websocket.connection import MarketFeedConnection
from brokers.dhan.websocket.publish import MarketFeedPublisher
from brokers.dhan.websocket.subscription import MarketFeedSubscriptionManager
from domain.lifecycle_health import HealthStatus
from domain.ports.time_service import get_current_clock
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.lifecycle.lifecycle import HealthState, ManagedService

logger = logging.getLogger(__name__)


class DhanMarketFeed(ReconnectingServiceMixin, ManagedService):
    """Wraps the SDK's MarketFeed for real-time market data.

    Supports reconnect backfill: on reconnection, if a ``backfill_callback``
    was provided, it is invoked to fetch missed bars between the last tick
    time and the reconnection time.  The returned bars are published as TICK
    events so downstream subscribers see no gap.

    Implements :class:`ManagedService` (Phase B / B5) so the broker's
    :class:`LifecycleManager` can start, stop, and health-check the
    background thread.

    Composes two extracted components:

    - ``self._conn`` (:class:`MarketFeedConnection`) — connection lifecycle
    - ``self._sub`` (:class:`MarketFeedSubscriptionManager`) — subscription
      and callback management
    """

    name = "dhan.market_feed"
    MAX_INSTRUMENTS = 1000  # Dhan WebSocket limit per connection

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        resolver=None,
        access_token_fn: Callable[[], str] | None = None,
        event_bus: EventBus | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        admission: MarketFeedConnectionAdmission | None = None,
    ):
        """Initialize market feed.

        Args:
            client_id: Dhan client ID
            access_token: Dhan access token (static snapshot)
            access_token_fn: Callable returning fresh token (preferred over static)
            instruments: List of (exchange, security_id, mode) tuples.
            resolver: Optional SymbolResolver for security_id → symbol lookup
            event_bus: Optional EventBus to publish TICK/DEPTH events to.
            backfill_callback: ``(symbol, from_dt, to_dt) -> list[dict]``
                Called on reconnect to fill the gap.
            admission: Optional host-wide admission gate. Defaults to a real
                ``MarketFeedConnectionAdmission``.
        """
        # Shared state.
        self._lock = threading.RLock()

        # Context and resolver.
        self._context = _DhanContext(
            client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
        )
        self._raw_instruments = instruments or []
        self._resolver = resolver
        self._event_bus = event_bus
        self._backfill_callback = backfill_callback

        # Plan §7.2: shared reconnect / message-tracking state (from mixin).
        self._init_reconnect_state()

        # Fallback sequence counters for partial construction (unit tests).
        self._sequence_counters: dict[str, int] = {}

        # --- Create extracted components ---

        # Subscription manager (owns instrument list, callbacks, tick tracking).
        self._sub = MarketFeedSubscriptionManager(
            instruments=self._raw_instruments,
            lock=self._lock,
            feed_ref=self,
        )

        # Connection manager (owns SDK feed, thread, admission, reconnect loop).
        self._conn = MarketFeedConnection(
            feed_ref=self,
            client_id=client_id,
            context=self._context,
            subscribed_instruments_getter=lambda: self._sub.subscribed_instruments,
            lock=self._lock,
            stop_event=self._stop_event,
            name=self.name,
        )

        # Wire up optional injection for the admission gate.
        if admission is not None:
            self._conn._set_admission_for_test(admission)

        self._publisher = MarketFeedPublisher(
            event_bus,
            self._next_sequence,
            to_decimal=_to_decimal,
        )

    # ------------------------------------------------------------------
    # Compatibility surface — attributes historically on the facade
    # ------------------------------------------------------------------

    @property
    def _instruments(self) -> list[tuple]:
        if getattr(self, "_sub", None) is not None:
            return self._sub._instruments
        return getattr(self, "__instruments_fallback", [])

    @_instruments.setter
    def _instruments(self, value: list[tuple]) -> None:
        if getattr(self, "_sub", None) is not None:
            self._sub._instruments = value
        else:
            object.__setattr__(self, "__instruments_fallback", value)

    @property
    def _subscribed_instruments(self) -> set:
        if getattr(self, "_sub", None) is not None:
            return self._sub._subscribed_instruments
        return getattr(self, "__subscribed_instruments_fallback", set())

    @_subscribed_instruments.setter
    def _subscribed_instruments(self, value: set) -> None:
        if getattr(self, "_sub", None) is not None:
            self._sub._subscribed_instruments = value
        else:
            object.__setattr__(self, "__subscribed_instruments_fallback", value)

    @property
    def _quote_callbacks(self) -> list:
        if getattr(self, "_sub", None) is not None:
            return self._sub._quote_callbacks
        if not hasattr(self, "__quote_callbacks_fallback"):
            object.__setattr__(self, "__quote_callbacks_fallback", [])
        return getattr(self, "__quote_callbacks_fallback")

    @_quote_callbacks.setter
    def _quote_callbacks(self, value: list) -> None:
        if getattr(self, "_sub", None) is not None:
            self._sub._quote_callbacks = value
        else:
            object.__setattr__(self, "__quote_callbacks_fallback", value)

    @property
    def _depth_callbacks(self) -> list:
        if getattr(self, "_sub", None) is not None:
            return self._sub._depth_callbacks
        if not hasattr(self, "__depth_callbacks_fallback"):
            object.__setattr__(self, "__depth_callbacks_fallback", [])
        return getattr(self, "__depth_callbacks_fallback")

    @_depth_callbacks.setter
    def _depth_callbacks(self, value: list) -> None:
        if getattr(self, "_sub", None) is not None:
            self._sub._depth_callbacks = value
        else:
            object.__setattr__(self, "__depth_callbacks_fallback", value)

    @property
    def _last_tick_time(self) -> dict[str, datetime]:
        if getattr(self, "_sub", None) is not None:
            return self._sub._last_tick_time
        if not hasattr(self, "__last_tick_time_fallback"):
            object.__setattr__(self, "__last_tick_time_fallback", {})
        return getattr(self, "__last_tick_time_fallback")

    @property
    def _feed(self) -> Any | None:
        if getattr(self, "_conn", None) is not None:
            return self._conn.feed
        return getattr(self, "__feed_fallback", None)

    @_feed.setter
    def _feed(self, value: Any | None) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn.feed = value
        else:
            object.__setattr__(self, "__feed_fallback", value)

    @property
    def _thread(self) -> threading.Thread | None:
        if getattr(self, "_conn", None) is not None:
            return self._conn.thread
        return getattr(self, "__thread_fallback", None)

    @_thread.setter
    def _thread(self, value: threading.Thread | None) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn._thread = value
        else:
            object.__setattr__(self, "__thread_fallback", value)

    @property
    def _disconnect_time(self) -> datetime | None:
        if getattr(self, "_conn", None) is not None:
            return self._conn._disconnect_time
        return getattr(self, "__disconnect_time_fallback", None)

    @_disconnect_time.setter
    def _disconnect_time(self, value: datetime | None) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn._disconnect_time = value
        else:
            object.__setattr__(self, "__disconnect_time_fallback", value)

    @property
    def _reconnect_count(self) -> int:
        if getattr(self, "_conn", None) is not None:
            return self._conn._reconnect_count
        return getattr(self, "__reconnect_count_fallback", 0)

    @_reconnect_count.setter
    def _reconnect_count(self, value: int) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn._reconnect_count = value
        else:
            object.__setattr__(self, "__reconnect_count_fallback", value)

    @property
    def _last_message_at(self) -> datetime | None:
        if getattr(self, "_conn", None) is not None:
            return self._conn._last_message_at
        return getattr(self, "__last_message_at_fallback", None)

    @_last_message_at.setter
    def _last_message_at(self, value: datetime | None) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn._last_message_at = value
        else:
            object.__setattr__(self, "__last_message_at_fallback", value)

    @property
    def _is_connected(self) -> bool:
        if getattr(self, "_conn", None) is not None:
            return self._conn._is_connected
        return getattr(self, "__is_connected_fallback", False)

    @_is_connected.setter
    def _is_connected(self, value: bool) -> None:
        if getattr(self, "_conn", None) is not None:
            self._conn._is_connected = value
        else:
            object.__setattr__(self, "__is_connected_fallback", value)

    def _on_close(self, feed) -> None:
        """Compatibility shim — SDK close callback lives on connection."""
        self._conn._on_close(feed)

    def _on_connect(self, feed) -> None:
        """Compatibility shim — SDK connect callback lives on connection."""
        self._conn._on_connect(feed)

    def _on_error(self, feed, error) -> None:
        """Compatibility shim — SDK error callback lives on connection."""
        self._conn._on_error(feed, error)

    def _track_tick_time(self, quote: dict) -> None:
        """Compatibility shim — tick tracking lives on subscription manager."""
        self._sub.track_tick_time(quote)

    # ------------------------------------------------------------------
    # Public API — connection lifecycle (delegated to self._conn)
    # ------------------------------------------------------------------

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        self._conn.update_token(access_token)

    def connect(self) -> None:
        """Start the WebSocket connection in a background daemon thread."""
        if getattr(self, "_conn", None) is not None:
            self._conn.connect()
        else:
            self.start()

    def start(self) -> None:
        """ManagedService protocol: start the WebSocket thread.

        Idempotent — re-calling while the thread is alive is a no-op.
        """
        if getattr(self, "_conn", None) is not None:
            self._conn.start()
        else:
            thread = getattr(self, "_thread", None)
            if thread and thread.is_alive():
                return
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run, name=getattr(self, "name", "dhan.market_feed"), daemon=True
            )
            object.__setattr__(self, "__thread_fallback", thread)
            thread.start()

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Stop the WebSocket connection."""
        if getattr(self, "_conn", None) is not None:
            self._conn.disconnect(timeout_seconds=timeout_seconds)
        else:
            self.stop(timeout_seconds=timeout_seconds)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the WebSocket thread."""
        if getattr(self, "_conn", None) is not None:
            self._conn.stop(timeout_seconds=timeout_seconds)
        else:
            self._stop_event.set()
            thread = getattr(self, "_thread", None)
            if thread and thread.is_alive():
                thread.join(timeout=timeout_seconds)

    @property
    def is_connected(self) -> bool:
        """Return True if the feed is connected and not stale."""
        if getattr(self, "_conn", None) is not None:
            return self._conn.is_connected
        return bool(getattr(self, "_is_connected", False))

    # ------------------------------------------------------------------
    # Public API — subscriptions (delegated to self._sub)
    # ------------------------------------------------------------------

    def subscribe(self, instruments: list[tuple]) -> None:
        """Add instruments to the subscription."""
        self._sub.subscribe(instruments)

    def unsubscribe(self, instruments: list[tuple]) -> None:
        """Remove instruments from the subscription."""
        self._sub.unsubscribe(instruments)

    def on_quote(self, callback: Callable[[dict], None]) -> None:
        """Register callback for quote updates."""
        self._sub.on_quote(callback)

    def on_depth(self, callback: Callable[[dict], None]) -> None:
        """Register callback for depth updates."""
        self._sub.on_depth(callback)

    def off_quote(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered quote callback."""
        self._sub.off_quote(callback)

    def off_depth(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered depth callback."""
        self._sub.off_depth(callback)

    # ------------------------------------------------------------------
    # Message processing (bridges connection → subscription → publish)
    # ------------------------------------------------------------------

    def _on_message(self, feed, data: dict) -> None:
        """SDK message callback — transform, track, and publish."""
        if not data:
            return
        if getattr(self, "_conn", None) is not None:
            self._conn._note_message_received()
            with self._lock:
                if self._conn._message_count % 100 == 0 and getattr(self, "_sub", None) is not None:
                    self._sub.cleanup_stale_tick_tracking()
        data_type = data.get("type", "")
        if data_type in ("Ticker Data", "Quote Data"):
            quote = self._transform_quote(data)
            if getattr(self, "_sub", None) is not None:
                self._sub.track_tick_time(quote)
                callbacks = self._sub.snapshot_quote_callbacks()
            else:
                callbacks = []
            for cb in callbacks:
                try:
                    cb(quote)
                except Exception as exc:
                    logger.error("Quote callback error: %s", exc)
            corr = (
                self._sub.gen_ws_correlation_id()
                if getattr(self, "_sub", None) is not None
                else None
            )
            self._publish_tick(quote, correlation_id=corr)
        elif data_type in ("Market Depth", "Full Data"):
            depth = self._transform_depth(data)
            if getattr(self, "_sub", None) is not None:
                callbacks = self._sub.snapshot_depth_callbacks()
                corr_id = self._sub.gen_ws_correlation_id()
            else:
                callbacks = []
                corr_id = None
            for cb in callbacks:
                try:
                    cb(depth)
                except Exception as exc:
                    logger.error("Depth callback error: %s", exc)
            self._publish_depth(depth, correlation_id=corr_id)
            # Full Data frames carry quote fields; publish tick too for FULL mode.
            if data_type == "Full Data":
                quote = self._transform_quote(data)
                if getattr(self, "_sub", None) is not None:
                    self._sub.track_tick_time(quote)
                    quote_callbacks = self._sub.snapshot_quote_callbacks()
                else:
                    quote_callbacks = []
                for cb in quote_callbacks:
                    try:
                        cb(quote)
                    except Exception as exc:
                        logger.error("Quote callback error: %s", exc)
                self._publish_tick(quote, correlation_id=corr_id)
        else:
            if data_type not in ("Previous Close", "OI Data", "Market Status"):
                logger.debug(
                    "dhan_ws_unknown_packet_type",
                    extra={"data_type": data_type, "keys": list(data.keys())},
                )

    def _backfill_gap(self, disconnect_time: datetime) -> None:
        """Fetch missed bars from REST and publish as TICK events."""
        if self._backfill_callback is None:
            return
        now = get_current_clock().now()
        if disconnect_time >= now:
            return
        if getattr(self, "_sub", None) is None:
            return
        symbol_times = self._sub.symbol_tick_times()
        symbols = list(symbol_times.keys())
        if not symbols:
            return
        logger.info(
            "Backfilling %d symbols for gap %s → %s",
            len(symbols),
            disconnect_time.isoformat(),
            now.isoformat(),
        )
        for symbol in symbols:
            try:
                bars = self._backfill_callback(symbol, disconnect_time, now)
                for bar in bars:
                    ts = bar.get("timestamp")
                    if ts is None:
                        bar["timestamp"] = now
                    self._publish_tick(bar)
                    bar_ts = bar.get("timestamp", now)
                    if isinstance(bar_ts, datetime):
                        prev = symbol_times.get(symbol)
                        if prev is None or bar_ts > prev:
                            symbol_times[symbol] = bar_ts
                if bars:
                    logger.debug("Backfilled %d bars for %s", len(bars), symbol)
            except Exception as exc:
                logger.warning("Backfill failed for %s: %s", symbol, exc)

    # ------------------------------------------------------------------
    # Data transformation — thin wrappers over pure helpers
    # ------------------------------------------------------------------

    def _transform_quote(self, data: dict) -> dict:
        return _transform_quote(data, getattr(self, "_resolver", None))

    @staticmethod
    def _normalize_sdk_depth(raw_depth: Any) -> dict[str, list[dict[str, Any]]]:
        return _normalize_sdk_depth(raw_depth)

    def _transform_depth(self, data: dict) -> dict:
        return _transform_depth(data, getattr(self, "_resolver", None))

    def _next_sequence(self, symbol: str) -> int:
        """Monotonic per-symbol sequence (uses sub manager when available)."""
        if getattr(self, "_sub", None) is not None:
            return self._sub.next_sequence(symbol)
        counters = getattr(self, "_sequence_counters", None)
        if counters is None:
            self._sequence_counters = {}
            counters = self._sequence_counters
        seq = counters.get(symbol, 0) + 1
        counters[symbol] = seq
        return seq

    # ------------------------------------------------------------------
    # Publishing pipeline (delegated)
    # ------------------------------------------------------------------

    def _publish_tick(self, quote: dict, correlation_id: str | None = None) -> None:
        """Publish a tick to the event bus under strict mode."""
        pub = getattr(self, "_publisher", None)
        if pub is None:
            return
        pub.publish_tick(quote, correlation_id=correlation_id)

    def _publish_depth(self, depth: dict, correlation_id: str | None = None) -> None:
        """Publish a depth snapshot under strict mode."""
        pub = getattr(self, "_publisher", None)
        if pub is None:
            return
        pub.publish_depth(depth, correlation_id=correlation_id)

    @property
    def _published_ticks(self) -> int:
        pub = getattr(self, "_publisher", None)
        return pub.published_ticks if pub is not None else 0

    @property
    def _dropped_ticks(self) -> int:
        pub = getattr(self, "_publisher", None)
        return pub.dropped_ticks if pub is not None else 0

    @property
    def _published_depths(self) -> int:
        pub = getattr(self, "_publisher", None)
        return pub.published_depths if pub is not None else 0

    @property
    def _dropped_depths(self) -> int:
        pub = getattr(self, "_publisher", None)
        return pub.dropped_depths if pub is not None else 0

    # ------------------------------------------------------------------
    # Health (bridges connection + publish counters)
    # ------------------------------------------------------------------

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        from config.ws_settings import (
            DHAN_MAX_RECONNECT_ATTEMPTS,
            DHAN_STALENESS_THRESHOLD_SECONDS,
        )

        if getattr(self, "_conn", None) is not None:
            snap = self._conn.health_snapshot()
        else:
            # Partial construction (unit tests that bypass __init__).
            thread = getattr(self, "_thread", None)
            thread_alive = bool(thread and thread.is_alive())
            is_connected = bool(getattr(self, "_is_connected", False))
            snap = {
                "thread_alive": thread_alive,
                "is_connected": is_connected,
                "reconnect_count": int(getattr(self, "_reconnect_count", 0)),
                "last_message_age": None,
                "admission_blocked": False,
                "is_stale": False,
                "staleness_threshold": DHAN_STALENESS_THRESHOLD_SECONDS,
                "admission_status": {},
            }

        if snap["thread_alive"] and snap["is_connected"] and not snap["is_stale"]:
            state = HealthState.HEALTHY
            detail = "running and connected"
        elif snap["thread_alive"] and snap["admission_blocked"]:
            state = HealthState.DEGRADED
            detail = "market_feed_connection_lock_held by another process on this host"
        elif (
            snap["thread_alive"]
            and isinstance(snap["admission_status"], dict)
            and snap["admission_status"].get("seconds_until_connect_allowed", 0) > 0
        ):
            state = HealthState.DEGRADED
            detail = "waiting for rate-limit cooldown before next handshake"
        elif snap["thread_alive"] and snap["is_connected"] and snap["is_stale"]:
            state = HealthState.DEGRADED
            detail = "connected but stale; reconnect watchdog should close transport"
        elif snap["thread_alive"] and not snap["is_connected"]:
            state = HealthState.DEGRADED
            detail = "thread running but feed not connected (reconnecting?)"
        else:
            state = HealthState.STOPPED
            detail = "not started"

        return HealthStatus(
            state=state,
            service=self.name,
            last_check=get_current_clock().now(),
            detail=detail,
            metrics={
                "connected": snap["is_connected"],
                "thread_alive": snap["thread_alive"],
                "reconnect_count": snap["reconnect_count"],
                "max_reconnect_attempts": DHAN_MAX_RECONNECT_ATTEMPTS,
                "published_ticks": self._published_ticks,
                "dropped_ticks": self._dropped_ticks,
                "published_depths": self._published_depths,
                "dropped_depths": self._dropped_depths,
                "last_message_age_seconds": (
                    snap["last_message_age"] if snap["last_message_age"] is not None else -1
                ),
                "is_stale": snap["is_stale"],
                "staleness_threshold_seconds": snap["staleness_threshold"],
                **snap["admission_status"],
            },
        )

    # ------------------------------------------------------------------
    # Reconnect backfill tracking (delegated to sub)
    # ------------------------------------------------------------------

    def clear_symbol_tracking(self, symbol: str) -> None:
        """Remove last-tick-time tracking for a symbol (called on unsubscribe)."""
        self._sub.clear_symbol_tracking(symbol)

    def _run(self) -> None:
        """Compatibility shim — run connection loop."""
        if getattr(self, "_conn", None) is not None:
            self._conn._run()
