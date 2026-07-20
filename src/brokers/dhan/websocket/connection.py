"""MarketFeedConnection — WebSocket lifecycle and reconnection logic.

Extracted from the former ``DhanMarketFeed`` class in ``market_feed.py``
as part of the connection-management modularization (Task 2).  Owns the
SDK feed object, background thread, admission gate, reconnection loop,
backoff, health tracking, and the ``on_connect/on_close/on_error`` SDK
callbacks.

The parent ``DhanMarketFeed`` creates one instance and delegates all
connection lifecycle calls to it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from brokers.dhan.streaming.connection_admission import MarketFeedConnectionAdmission
from brokers.dhan.websocket._helpers import _DhanContext, _sdk_market_feed_class
from config.ws_settings import (
    DHAN_BACKOFF_BASE_DELAY_MS,
    DHAN_BACKOFF_MAX_DELAY_MS,
    DHAN_INITIAL_BACKOFF_SECONDS,
    DHAN_MAX_RECONNECT_ATTEMPTS,
    DHAN_RECONNECT_COOLDOWN_SECONDS,
    DHAN_STALENESS_THRESHOLD_SECONDS,
)
from domain.ports.time_service import get_current_clock

logger = logging.getLogger(__name__)


class MarketFeedConnection:
    """Manages the WebSocket connection lifecycle for DhanMarketFeed.

    Handles connect/disconnect/reconnect loops, admission control,
    backoff, and SDK feed construction/teardown.  Delegates message
    processing and subscription management back to the parent
    ``DhanMarketFeed`` via callbacks.

    Thread safety is provided by the parent's ``_lock`` (an ``RLock``)
    which is shared across ``MarketFeedConnection``, the parent, and
    ``MarketFeedSubscriptionManager`` so that state invariants that
    span multiple components remain atomic.
    """

    def __init__(
        self,
        *,
        feed_ref: Any,
        client_id: str,
        context: _DhanContext,
        subscribed_instruments_getter: Callable[[], set],
        lock: threading.RLock,
        stop_event: threading.Event,
        name: str = "dhan.market_feed",
    ) -> None:
        """Initialise the connection manager.

        Args:
            feed_ref: Backreference to the parent ``DhanMarketFeed`` so
                callbacks like ``_on_connect`` and ``_on_message`` can
                reach subscription / publish methods.
            client_id: Dhan client ID (for admission gate).
            context: SDK context for token/credentials.
            subscribed_instruments_getter: Callable that returns the
                current set of subscribed instruments (used to replay
                subscriptions on reconnect).
            lock: Shared ``RLock`` from the parent.
            stop_event: Shared ``Event`` from the parent.
            name: Thread name for the background connection thread.
        """
        self._feed_ref = feed_ref
        self._client_id = client_id
        self._context = context
        self._get_subscribed = subscribed_instruments_getter
        self._lock = lock
        self._stop_event = stop_event
        self._name = name

        # SDK feed and thread — owned exclusively here.
        self._feed: Any | None = None
        self._thread: threading.Thread | None = None

        # Set by ``_run()`` immediately before it hands the SDK feed's private
        # event loop to ``feed.run()``. ``stop()`` waits on this before
        # touching the feed, so it never races the background thread's first
        # ``loop.run_until_complete()`` call for ownership of that loop (see
        # ``_close_sdk_feed`` docstring for the underlying SDK quirk).
        self._run_claimed = threading.Event()

        # Connection state.
        self._is_connected = False
        self._connected_at: datetime | None = None
        self._disconnect_time: datetime | None = None
        self._last_message_at: datetime | None = None
        self._message_count = 0
        self._reconnect_count = 0

        # Admission gate — injectable via _set_admission_for_test.
        self._admission: MarketFeedConnectionAdmission | None = MarketFeedConnectionAdmission(
            client_id
        )
        self._admission_blocked = False

    # ------------------------------------------------------------------
    # Public API — thin wrappers that the parent facade delegates to
    # ------------------------------------------------------------------

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        if not access_token or access_token == self._context.get_access_token():
            return
        self._context.update_token(access_token)
        with self._lock:
            if self._feed:
                self._feed.access_token = access_token
                ws = getattr(self._feed, "ws", None)
                loop = getattr(self._feed, "loop", None)
                if ws and loop and loop.is_running():
                    try:
                        asyncio.run_coroutine_threadsafe(ws.close(), loop)
                    except Exception as exc:
                        logger.warning("Error closing feed websocket on token update: %s", exc)

    def start(self) -> bool:
        """Start the WebSocket connection in a background daemon thread.

        Returns True if the thread was started, False if already
        running or no instruments are available.
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Market feed already connected")
                return False

            if not self._get_subscribed():
                logger.debug("No valid instruments to subscribe yet")
                return False

            self._stop_event.clear()
            self._run_claimed.clear()
            self._is_connected = False
            self._build_sdk_feed_locked()

            self._thread = threading.Thread(
                target=self._run,
                name=self._name,
                daemon=True,
            )
            self._thread.start()
            return True

    def connect(self) -> None:
        """Deprecated alias for :meth:`start`."""
        self.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """Stop the WebSocket thread and release the admission lock.

        Idempotent: a second call is a no-op.  Joins the thread within
        *timeout_seconds*; if the thread is still alive after the
        timeout, a warning is logged (the daemon thread will be reaped
        at process exit).
        """
        self._stop_event.set()
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            feed = self._feed
            thread = self._thread
        if feed:
            # Give the background thread a chance to claim the SDK feed's
            # event loop (via ``feed.run()``) before we touch it. Without
            # this, a stop() that lands before the thread reaches that call
            # races the thread's first ``loop.run_until_complete()`` for
            # ownership of the same loop object and raises "This event loop
            # is already running". Only waited when a feed actually exists —
            # a connection that was never started has nothing to claim.
            self._run_claimed.wait(timeout=2.0)
            self._close_sdk_feed(feed)
        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning("%s thread did not stop within %ss", self._name, timeout_seconds)
        if self._admission is not None:
            self._admission.release()
        logger.info("Market feed stopped")

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Deprecated alias for :meth:`stop`."""
        self.stop(timeout_seconds=timeout_seconds)

    @property
    def is_connected(self) -> bool:
        """Return True if the feed is connected and not stale."""
        with self._lock:
            age = self._last_activity_age_seconds_locked()
            is_stale = (
                self._is_connected and age is not None and age > self._staleness_threshold_seconds()
            )
            return self._is_connected and not is_stale

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    @property
    def feed(self) -> Any | None:
        return self._feed

    # ------------------------------------------------------------------
    # Internal — connection loop and SDK feed management
    # ------------------------------------------------------------------

    def _build_sdk_feed_locked(self) -> Any:
        """Create a fresh SDK feed from the current subscription snapshot."""
        self._feed = _sdk_market_feed_class()(
            dhan_context=self._context,
            instruments=list(self._get_subscribed()),
            on_connect=self._on_connect,
            on_message=self._feed_ref._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        return self._feed

    def _run(self) -> None:
        """Run the market feed event loop with reconnection backoff + inline staleness check.

        Staleness detection is handled here rather than in a separate
        watchdog thread: after each SDK ``run()`` or exception, if the
        feed was active but silent for longer than
        ``DHAN_STALENESS_THRESHOLD_SECONDS``, we close the socket before
        backing off.
        """
        backoff = DHAN_INITIAL_BACKOFF_SECONDS
        max_reconnect_attempts = DHAN_MAX_RECONNECT_ATTEMPTS
        staleness_threshold = DHAN_STALENESS_THRESHOLD_SECONDS

        while not self._stop_event.is_set():
            # ── Admission: only one process per account may own the WS slot ──
            admission = self._admission
            if admission is not None and not admission.lock_held:
                if not admission.try_acquire():
                    with self._lock:
                        self._admission_blocked = True
                    if self._stop_event.wait(timeout=5.0):
                        break
                    continue
                with self._lock:
                    self._admission_blocked = False

            # ── 429 cooldown ──────────────────────────────────────────────────
            if admission is not None:
                cooldown_wait = admission.seconds_until_connect_allowed()
                if cooldown_wait > 0:
                    logger.info(
                        "market_feed_connect_cooldown_wait",
                        extra={"seconds": round(cooldown_wait, 2)},
                    )
                    if self._stop_event.wait(timeout=min(cooldown_wait, 5.0)):
                        break
                    continue

            # ── Max reconnect guard ───────────────────────────────────────────
            with self._lock:
                current_reconnects = self._reconnect_count

            if current_reconnects >= max_reconnect_attempts:
                logger.critical(
                    "max_reconnect_attempts_exceeded",
                    extra={"attempts": current_reconnects, "max_attempts": max_reconnect_attempts},
                )
                self._emit_reconnect_metric()
                logger.warning(
                    "market_feed_reconnect_cooldown",
                    extra={"cooldown_seconds": DHAN_RECONNECT_COOLDOWN_SECONDS},
                )
                if self._stop_event.wait(timeout=DHAN_RECONNECT_COOLDOWN_SECONDS):
                    break
                with self._lock:
                    self._reconnect_count = 0
                logger.info("market_feed_reconnect_cooldown_complete")
                continue

            # ── Inline staleness check ────────────────────────────────────────
            stale_feed = None
            with self._lock:
                if self._is_connected:
                    age = self._last_activity_age_seconds_locked()
                    if age is not None and age > staleness_threshold:
                        logger.warning(
                            "market_feed_stale_reconnect_forced",
                            extra={"age_seconds": age, "threshold_seconds": staleness_threshold},
                        )
                        stale_feed = self._feed
                        self._is_connected = False
                        self._connected_at = None
                        self._disconnect_time = get_current_clock().now()
                        self._reconnect_count += 1
                        self._feed = None
            if stale_feed is not None:
                self._emit_reconnect_metric()
                with contextlib.suppress(Exception):
                    stale_feed.close_connection()
                if self._stop_event.wait(timeout=backoff):
                    break
                from brokers.common.backoff import exponential_backoff

                backoff = exponential_backoff(
                    current_reconnects,
                    base_delay_ms=DHAN_BACKOFF_BASE_DELAY_MS,
                    max_delay_ms=DHAN_BACKOFF_MAX_DELAY_MS,
                )
                continue

            # ── Run the SDK ───────────────────────────────────────────────────
            try:
                with self._lock:
                    feed = self._feed or self._build_sdk_feed_locked()
                self._run_claimed.set()
                feed.run()
                # Successful return → clean close → reset backoff fast
                backoff = DHAN_INITIAL_BACKOFF_SECONDS
                with self._lock:
                    self._is_connected = False
                    self._connected_at = None
                    self._disconnect_time = self._disconnect_time or get_current_clock().now()
                    self._feed = None
                    self._reconnect_count += 1
                self._emit_reconnect_metric()

            except Exception as exc:
                err_str = str(exc).lower()
                if "no close frame" in err_str:
                    logger.debug("WebSocket closed without close frame (expected)")
                    backoff = DHAN_INITIAL_BACKOFF_SECONDS
                elif "429" in err_str:
                    logger.warning("WebSocket rate limited, backing off %ss", backoff)
                    if admission is not None:
                        admission.record_rate_limit_cooldown()
                else:
                    logger.error("Market feed error: %s", exc)

                with self._lock:
                    age = (
                        (get_current_clock().now() - self._last_message_at).total_seconds()
                        if self._last_message_at is not None
                        else 0.0
                    )
                if age > staleness_threshold:
                    logger.warning(
                        "feed_stale_before_reconnect",
                        extra={"age_seconds": age, "threshold_seconds": staleness_threshold},
                    )

                with self._lock:
                    self._reconnect_count += 1
                    self._is_connected = False
                    self._connected_at = None
                    self._disconnect_time = self._disconnect_time or get_current_clock().now()
                    old_feed = self._feed
                    self._feed = None
                if old_feed is not None:
                    with contextlib.suppress(Exception):
                        old_feed.close_connection()
                self._emit_reconnect_metric()

            # ── Backoff before next reconnect attempt ─────────────────────────
            if self._stop_event.is_set():
                break
            if self._stop_event.wait(timeout=backoff):
                break
            from brokers.common.backoff import exponential_backoff

            backoff = exponential_backoff(
                current_reconnects,
                base_delay_ms=DHAN_BACKOFF_BASE_DELAY_MS,
                max_delay_ms=DHAN_BACKOFF_MAX_DELAY_MS,
            )

        # Always release the host-wide admission lock on exit.
        if admission is not None:
            admission.release()

    def _close_sdk_feed(self, feed: Any, timeout_seconds: float = 2.0) -> None:
        """Close the Dhan SDK's feed object without conflicting with a caller's loop.

        The SDK's ``close_connection()`` looks synchronous but internally
        drives its own coroutine; when called from a thread that already
        has a running asyncio event loop, the SDK's internal loop handling
        raises "Cannot run the event loop while another loop is running".
        Running the close on a separate thread avoids this.
        """
        try:
            asyncio.get_running_loop()
            has_running_loop = True
        except RuntimeError:
            has_running_loop = False

        if not has_running_loop:
            try:
                feed.close_connection()
            except Exception as exc:
                logger.warning("Error closing market feed: %s", exc)
            return

        close_thread = threading.Thread(
            target=self._close_sdk_feed_worker,
            args=(feed,),
            name="dhan.market_feed.close",
            daemon=True,
        )
        close_thread.start()
        close_thread.join(timeout=timeout_seconds)
        if close_thread.is_alive():
            logger.warning(
                "dhan.market_feed close_connection did not complete within %ss",
                timeout_seconds,
            )

    @staticmethod
    def _close_sdk_feed_worker(feed: Any) -> None:
        try:
            feed.close_connection()
        except Exception as exc:
            logger.warning("Error closing market feed: %s", exc)

    # ------------------------------------------------------------------
    # SDK callbacks (bound when building the feed)
    # ------------------------------------------------------------------

    def _on_connect(self, feed) -> None:
        with self._lock:
            was_connected = self._is_connected
            self._is_connected = True
            self._connected_at = get_current_clock().now()
            self._reconnect_count = 0
            disconnect_time = self._disconnect_time
            self._disconnect_time = None
            to_subscribe = list(self._get_subscribed())
        logger.info("Market feed connected")
        if self._admission is not None:
            self._admission.clear_cooldown()
        if to_subscribe and feed is not None:
            logger.info("Replaying %d market subscriptions on connect", len(to_subscribe))
            try:
                feed.subscribe_symbols(to_subscribe)
            except Exception as exc:
                with self._lock:
                    self._is_connected = False
                    self._connected_at = None
                    self._disconnect_time = get_current_clock().now()
                logger.error("Failed to replay market subscriptions: %s", exc)
                with contextlib.suppress(Exception):
                    feed.close_connection()
                return
        # On reconnect, backfill the gap via the parent
        if not was_connected and disconnect_time is not None:
            self._feed_ref._backfill_gap(disconnect_time)

    def _on_close(self, feed) -> None:
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            self._disconnect_time = get_current_clock().now()
        logger.info("Market feed disconnected")

    def _on_error(self, feed, error) -> None:
        logger.error("Market feed error: %s", error)
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            self._disconnect_time = get_current_clock().now()

    # ------------------------------------------------------------------
    # Health / staleness helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _staleness_threshold_seconds() -> float:
        """Return the staleness threshold for this connection."""
        return DHAN_STALENESS_THRESHOLD_SECONDS

    def _last_activity_age_seconds_locked(self) -> float | None:
        last_msg = getattr(self, "_last_message_at", None)
        conn_at = getattr(self, "_connected_at", None)
        references = [ts for ts in (last_msg, conn_at) if ts is not None]
        if not references:
            return None
        reference = max(references)
        return (get_current_clock().now() - reference).total_seconds()

    def _note_message_received(self) -> None:
        """Mark that a message was consumed (called from parent's _on_message)."""
        self._last_message_at = get_current_clock().now()
        self._message_count += 1

    # ------------------------------------------------------------------
    # Connection failure recording (encapsulation for subscription manager)
    # ------------------------------------------------------------------

    def record_connection_failure(self) -> None:
        """Record a connection failure from subscription manager.

        This method encapsulates state mutations that were previously done
        by directly accessing private attributes. Use this instead of
        ``self._is_connected = False``.
        """
        with self._lock:
            self._is_connected = False
            self._connected_at = None
            self._disconnect_time = get_current_clock().now()
            self._reconnect_count += 1

    def _emit_reconnect_metric(self) -> None:
        try:
            from brokers.dhan.resilience.metrics import dhan_ws_reconnect_total

            dhan_ws_reconnect_total.inc()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Health status (pulled by DhanMarketFeed.health())
    # ------------------------------------------------------------------

    def health_snapshot(self) -> dict:
        """Return a dict of connection-related health metrics.

        Called by ``DhanMarketFeed.health()`` which adds publish
        counters and builds the final ``HealthStatus``.
        """
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = self._is_connected
            reconnect_count = self._reconnect_count
            last_message_age = self._last_activity_age_seconds_locked()
            admission_blocked = self._admission_blocked

        admission_status = self._admission.status() if self._admission is not None else {}

        staleness_threshold = self._staleness_threshold_seconds()
        is_stale = (
            (last_message_age is not None and last_message_age > staleness_threshold)
            if last_message_age is not None
            else False
        )

        return {
            "thread_alive": thread_alive,
            "is_connected": is_connected,
            "reconnect_count": reconnect_count,
            "last_message_age": last_message_age,
            "admission_blocked": admission_blocked,
            "is_stale": is_stale,
            "staleness_threshold": staleness_threshold,
            "admission_status": admission_status,
        }

    # ------------------------------------------------------------------
    # Test support
    # ------------------------------------------------------------------

    def _set_admission_for_test(self, admission: MarketFeedConnectionAdmission | None) -> None:
        """Override the admission gate (used in tests to inject a no-op gate)."""
        self._admission = admission
