"""DhanMarketFeed — real-time market data via Dhan SDK WebSocket.

Extracted connection lifecycle to :class:`MarketFeedConnection` and
subscription management to :class:`MarketFeedSubscriptionManager`
(Task 2).  This module is a thin facade that composes both managers
and owns the message transformation / publishing pipeline.

All existing import paths continue to work:

    from brokers.dhan.websocket import DhanMarketFeed
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from brokers.dhan.api.reconnecting_service import ReconnectingServiceMixin
from brokers.dhan.streaming.connection_admission import MarketFeedConnectionAdmission
from brokers.dhan.websocket._helpers import _DhanContext, _to_decimal, _to_sdk_instruments
from brokers.dhan.websocket.connection import MarketFeedConnection
from brokers.dhan.websocket.subscription import MarketFeedSubscriptionManager
from domain import DepthLevel, MarketDepth, Quote
from domain.events import DomainEvent
from infrastructure.event_bus.event_bus import EventBus
from domain.lifecycle_health import HealthStatus
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

        # Strict-mode publish counters (visible via health()).
        self._published_ticks = 0
        self._dropped_ticks = 0
        self._published_depths = 0
        self._dropped_depths = 0

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

    # ------------------------------------------------------------------
    # Public API — connection lifecycle (delegated to self._conn)
    # ------------------------------------------------------------------

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        self._conn.update_token(access_token)

    def connect(self) -> None:
        """Start the WebSocket connection in a background daemon thread."""
        self._conn.connect()

    def start(self) -> None:
        """ManagedService protocol: start the WebSocket thread.

        Idempotent — re-calling while the thread is alive is a no-op.
        """
        self._conn.start()

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Stop the WebSocket connection."""
        self._conn.disconnect(timeout_seconds=timeout_seconds)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the WebSocket thread."""
        self._conn.stop(timeout_seconds=timeout_seconds)

    @property
    def is_connected(self) -> bool:
        """Return True if the feed is connected and not stale."""
        return self._conn.is_connected

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
        self._conn._note_message_received()
        with self._lock:
            if self._conn._message_count % 100 == 0:
                self._sub.cleanup_stale_tick_tracking()
        data_type = data.get("type", "")
        if data_type in ("Ticker Data", "Quote Data"):
            quote = self._transform_quote(data)
            self._sub.track_tick_time(quote)
            callbacks = self._sub.snapshot_quote_callbacks()
            for cb in callbacks:
                try:
                    cb(quote)
                except Exception as exc:
                    logger.error("Quote callback error: %s", exc)
            self._publish_tick(quote, correlation_id=self._sub.gen_ws_correlation_id())
        elif data_type in ("Market Depth", "Full Data"):
            depth = self._transform_depth(data)
            callbacks = self._sub.snapshot_depth_callbacks()
            for cb in callbacks:
                try:
                    cb(depth)
                except Exception as exc:
                    logger.error("Depth callback error: %s", exc)
            corr_id = self._sub.gen_ws_correlation_id()
            self._publish_depth(depth, correlation_id=corr_id)
            # Full Data frames carry quote fields; publish tick too for FULL mode.
            if data_type == "Full Data":
                quote = self._transform_quote(data)
                self._sub.track_tick_time(quote)
                quote_callbacks = self._sub.snapshot_quote_callbacks()
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
        now = datetime.now(timezone.utc)
        if disconnect_time >= now:
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
    # Data transformation (pure, stateless)
    # ------------------------------------------------------------------

    def _transform_quote(self, data: dict) -> dict:
        security_id = str(data.get("security_id", ""))
        symbol = security_id
        if self._resolver:
            try:
                inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception as exc:
                logger.warning(
                    "dhan_ws_symbol_resolution_failed",
                    extra={"security_id": security_id, "exception_type": type(exc).__name__},
                )
        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "open": Decimal(str(data["open"])) if data.get("open") else None,
            "high": Decimal(str(data["high"])) if data.get("high") else None,
            "low": Decimal(str(data["low"])) if data.get("low") else None,
            "close": Decimal(str(data["close"])) if data.get("close") else None,
            "volume": int(data.get("volume", 0)),
            "change": Decimal("0"),
            "timestamp": datetime.now(timezone.utc),
        }

    @staticmethod
    def _normalize_sdk_depth(raw_depth: Any) -> dict[str, list[dict[str, Any]]]:
        """Convert Dhan SDK depth payload to {bids, asks} ladder dict."""
        if isinstance(raw_depth, dict):
            return {
                "bids": list(raw_depth.get("bids") or []),
                "asks": list(raw_depth.get("asks") or []),
            }
        if isinstance(raw_depth, list):
            bids: list[dict[str, Any]] = []
            asks: list[dict[str, Any]] = []
            for row in raw_depth:
                if not isinstance(row, dict):
                    continue
                bid_qty = int(row.get("bid_quantity") or 0)
                ask_qty = int(row.get("ask_quantity") or 0)
                if bid_qty > 0:
                    bids.append(
                        {
                            "price": row.get("bid_price", 0),
                            "quantity": bid_qty,
                            "orders": int(row.get("bid_orders") or 0),
                        }
                    )
                if ask_qty > 0:
                    asks.append(
                        {
                            "price": row.get("ask_price", 0),
                            "quantity": ask_qty,
                            "orders": int(row.get("ask_orders") or 0),
                        }
                    )
            return {"bids": bids, "asks": asks}
        return {"bids": [], "asks": []}

    def _transform_depth(self, data: dict) -> dict:
        security_id = str(data.get("security_id", ""))
        symbol = security_id
        if self._resolver:
            try:
                inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception as exc:
                logger.warning(
                    "dhan_ws_symbol_resolution_failed",
                    extra={"security_id": security_id, "exception_type": type(exc).__name__},
                )
        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "depth": self._normalize_sdk_depth(data.get("depth", [])),
        }

    # ------------------------------------------------------------------
    # Publishing pipeline
    # ------------------------------------------------------------------

    def _publish_tick(self, quote: dict, correlation_id: str | None = None) -> None:
        """Publish a tick to the event bus under strict mode."""
        if self._event_bus is None:
            return
        try:
            ltp_raw = quote.get("ltp")
            symbol = quote.get("symbol", "")
            ltp = _to_decimal(ltp_raw)
            if ltp_raw is None or ltp == 0:
                self._dropped_ticks += 1
                try:
                    from brokers.dhan.resilience.metrics import dhan_ws_dropped_ticks_total
                    dhan_ws_dropped_ticks_total.inc()
                except Exception:
                    pass
                logger.warning("tick_dropped_missing_or_zero_ltp: symbol=%s", symbol or "<unknown>")
                return
            if not symbol:
                self._dropped_ticks += 1
                try:
                    from brokers.dhan.resilience.metrics import dhan_ws_dropped_ticks_total
                    dhan_ws_dropped_ticks_total.inc()
                except Exception:
                    pass
                logger.warning("tick_dropped_missing_symbol")
                return

            seq = self._sub.next_sequence(symbol)
            quote["sequence"] = seq
            q = Quote(
                symbol=symbol,
                ltp=ltp,
                open=_to_decimal(quote.get("open")),
                high=_to_decimal(quote.get("high")),
                low=_to_decimal(quote.get("low")),
                close=_to_decimal(quote.get("close")),
                volume=quote.get("volume", 0),
                change=_to_decimal(quote.get("change")),
                timestamp=quote.get("timestamp"),
            )
            self._event_bus.publish(
                DomainEvent.now(
                    "TICK",
                    {"quote": q},
                    symbol=q.symbol,
                    source="DhanMarketFeed",
                    correlation_id=correlation_id,
                )
            )
            self._published_ticks += 1
            try:
                from brokers.dhan.resilience.metrics import dhan_ws_ticks_total
                dhan_ws_ticks_total.inc()
            except Exception:
                pass
        except Exception as exc:
            self._dropped_ticks += 1
            logger.error("EventBus TICK publish error: %s", exc)

    def _publish_depth(self, depth: dict, correlation_id: str | None = None) -> None:
        """Publish a depth snapshot under strict mode."""
        if self._event_bus is None:
            return
        symbol = depth.get("symbol", "")
        if not symbol:
            self._dropped_depths += 1
            logger.warning("depth_dropped_missing_symbol")
            return
        try:
            d = depth.get("depth", {}) or {}
            bids = [
                DepthLevel(
                    price=Decimal(str(b.get("price", 0))),
                    quantity=int(b.get("quantity", 0)),
                    orders=int(b.get("orders", 0)),
                )
                for b in d.get("bids", [])
            ]
            asks = [
                DepthLevel(
                    price=Decimal(str(a.get("price", 0))),
                    quantity=int(a.get("quantity", 0)),
                    orders=int(a.get("orders", 0)),
                )
                for a in d.get("asks", [])
            ]
            if not bids and not asks:
                self._dropped_depths += 1
                logger.warning("depth_dropped_both_sides_empty: symbol=%s", symbol)
                return
            if bids and bids[0].price <= 0:
                self._dropped_depths += 1
                logger.warning("depth_dropped_invalid_bid_top: symbol=%s bid0=%s", symbol, bids[0].price)
                return
            if asks and asks[0].price <= 0:
                self._dropped_depths += 1
                logger.warning("depth_dropped_invalid_ask_top: symbol=%s ask0=%s", symbol, asks[0].price)
                return
            md = MarketDepth(bids=bids, asks=asks)
            self._event_bus.publish(
                DomainEvent.now(
                    "DEPTH",
                    {"depth": md},
                    symbol=symbol,
                    source="DhanMarketFeed",
                    correlation_id=correlation_id,
                )
            )
            self._published_depths += 1
        except Exception as exc:
            self._dropped_depths += 1
            logger.error("EventBus DEPTH publish error: %s", exc)

    # ------------------------------------------------------------------
    # Health (bridges connection + publish counters)
    # ------------------------------------------------------------------

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        import os

        snap = self._conn.health_snapshot()

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
            last_check=datetime.now(timezone.utc),
            detail=detail,
            metrics={
                "connected": snap["is_connected"],
                "thread_alive": snap["thread_alive"],
                "reconnect_count": snap["reconnect_count"],
                "max_reconnect_attempts": int(os.getenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50")),
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
