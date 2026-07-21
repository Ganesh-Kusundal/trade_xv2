"""WebSocket connection management for BinaryDepthFeed.

Extracted from depth_feed_base.py to reduce god-object size. Contains the
WebSocket loop, start/stop lifecycle, health checks, token refresh,
subscription sending, and socket close logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from brokers.common.transport_policy import ResiliencePolicy
from config.ws_settings import DHAN_STALENESS_THRESHOLD_SECONDS
from domain.ports.time_service import get_current_clock
from domain.lifecycle_health import HealthStatus
from infrastructure.lifecycle.lifecycle import HealthState

logger = logging.getLogger(__name__)


class ConnectionMixin:
    """Mixin providing WebSocket connection management for BinaryDepthFeed."""

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Deprecated alias for :meth:`start`."""
        self.start()

    def start(self) -> None:
        """ManagedService protocol: start the WebSocket connection."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._websocket_loop,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        logger.info("%s_started", self.DEPTH_TYPE.lower())

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Deprecated alias for :meth:`stop`."""
        self.stop(timeout_seconds)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the WebSocket connection."""
        self._stop_event.set()

        with self._lock:
            ws = self._ws
            thread = self._thread

        if ws:
            self._close_active_websocket(ws, loop=getattr(self, "_ws_loop", None))

        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning(
                    "%s thread did not stop within %ss",
                    self.name,
                    timeout_seconds,
                )

        logger.info("%s_stopped", self.DEPTH_TYPE.lower())

    def close(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService-style alias for :meth:`stop`.

        The depth-200 connection pool eviction path and ``close_all`` call
        ``feed.close()``; without this alias those paths would raise
        ``AttributeError`` at runtime (see Depth200ConnectionPool.get_feed).
        """
        self.stop(timeout_seconds)

    @staticmethod
    def _staleness_threshold_seconds() -> float:
        """Application-level freshness threshold for the depth socket.

        Mirrors ``DhanMarketFeed._staleness_threshold_seconds`` so the two
        feeds honour the same ``DHAN_STALENESS_THRESHOLD_SECONDS`` knob.
        A connected-but-silent socket older than this is treated as dead
        and force-reconnected (see :meth:`_websocket_handler`).
        """
        return DHAN_STALENESS_THRESHOLD_SECONDS

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        threshold = self._staleness_threshold_seconds()
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = self._is_connected
            reconnect_count = self._reconnect_count
            last_message_age = (
                (get_current_clock().now() - self._last_message_at).total_seconds()
                if self._last_message_at is not None
                else None
            )

        is_stale = is_connected and last_message_age is not None and last_message_age > threshold

        if thread_alive and is_connected and not is_stale:
            state = HealthState.HEALTHY
            detail = "running and connected"
        elif thread_alive and is_connected and is_stale:
            state = HealthState.DEGRADED
            detail = "connected but stale (no messages received recently)"
        elif thread_alive and not is_connected:
            state = HealthState.DEGRADED
            detail = "thread running but not connected (reconnecting?)"
        else:
            state = HealthState.STOPPED
            detail = "not started"

        return HealthStatus(
            state=state,
            service=self.name,
            last_check=get_current_clock().now(),
            detail=detail,
            metrics={
                "reconnect_count": reconnect_count,
                "subscriptions": len(self._subscriptions),
                "depth_type": self.DEPTH_TYPE,
                "subscribed_instrument_count": len(self._subscriptions),
                "published_depths": self._published_depths,
                "dropped_depths": self._dropped_depths,
                "last_message_age_seconds": last_message_age
                if last_message_age is not None
                else -1,
                "is_stale": is_stale,
                "staleness_threshold_seconds": threshold,
            },
        )

    # ── WebSocket loop ─────────────────────────────────────────────────────

    def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect via shared ResiliencePolicy."""
        policy = ResiliencePolicy.for_dhan_ws()
        while not self._stop_event.is_set():
            try:
                self._connect_and_run()
            except Exception as exc:
                logger.error("%s_error: %s", self.DEPTH_TYPE.lower(), exc)

            if not self._stop_event.is_set():
                # Prefer mixin helper when available; fall back to policy delay.
                if hasattr(self, "_on_reconnect_failure"):
                    wait = self._on_reconnect_failure(
                        policy.delay_for(self._reconnect_count, with_jitter=False)
                    )
                else:
                    self._reconnect_count += 1
                    wait = policy.delay_for(self._reconnect_count, with_jitter=False)
                time.sleep(wait)

    def _connect_and_run(self) -> None:
        """Establish WebSocket connection and process messages."""
        import importlib.util

        if importlib.util.find_spec("websockets") is None:
            logger.error("websockets package not installed: pip install websockets")
            return

        logger.info("%s_connecting", self.DEPTH_TYPE.lower(), extra={"endpoint": self.ENDPOINT})

        # Run async WebSocket on a dedicated thread-owned loop (runtime boundary)
        from runtime.event_loop import new_dedicated_loop

        loop = new_dedicated_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop

        try:
            loop.run_until_complete(self._websocket_handler())
        finally:
            loop.close()
            with self._lock:
                self._ws_loop = None
                self._is_connected = False

    def _build_ws_url(self) -> str:
        """Build the authenticated WebSocket URL using the current token."""
        return f"{self.ENDPOINT}?token={self._access_token}&clientId={self._client_id}&authType=2"

    async def _websocket_handler(self) -> None:
        """Async WebSocket handler with auto-reconnect."""
        import websockets

        backoff = 1.0
        max_backoff = 30.0

        while not self._stop_event.is_set():
            # ── 429 cooldown ────────────────────────────────────────────────
            cooldown_wait = self._admission.seconds_until_connect_allowed()
            if cooldown_wait > 0:
                logger.info(
                    "%s_connect_cooldown_wait",
                    self.DEPTH_TYPE.lower(),
                    extra={"seconds": round(cooldown_wait, 2)},
                )
                await asyncio.sleep(min(cooldown_wait, 5.0))
                continue

            url = self._build_ws_url()
            try:
                async with websockets.connect(url) as ws:
                    with self._lock:
                        self._ws = ws
                        self._is_connected = True
                        self._reconnect_count = 0

                    logger.info("%s_connected", self.DEPTH_TYPE.lower())
                    self._admission.clear_cooldown()
                    # Freshness baseline: until the first real packet
                    # arrives, staleness is measured from connection time so
                    # a connected-but-silent socket still triggers healing.
                    self._last_message_at = get_current_clock().now()

                    if self._subscriptions:
                        self._send_subscription(self._subscriptions)

                    while not self._stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30.0)

                            if isinstance(message, bytes):
                                counters = {"published_depths": 0, "dropped_depths": 0}
                                self._parser.process_binary_message(
                                    message,
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

                            backoff = 1.0

                        except asyncio.TimeoutError:
                            # Self-healing staleness: ``ws.recv()`` blocks
                            # forever on a half-open (silent-but-connected)
                            # socket and never raises, so a dead connection
                            # would persist for the lifetime of the feed.
                            # If no message has arrived within the staleness
                            # threshold, tear the socket down and force the
                            # outer loop to reconnect.
                            threshold = self._staleness_threshold_seconds()
                            last_msg = self._last_message_at
                            age = (
                                (get_current_clock().now() - last_msg).total_seconds()
                                if last_msg is not None
                                else None
                            )
                            if age is not None and age > threshold:
                                logger.warning(
                                    "%s_stale_reconnect_forced",
                                    self.DEPTH_TYPE.lower(),
                                    extra={
                                        "age_seconds": round(age, 2),
                                        "threshold_seconds": threshold,
                                    },
                                )
                                with self._lock:
                                    self._is_connected = False
                                break
                            continue

                        except websockets.ConnectionClosed:
                            logger.warning("%s_connection_closed", self.DEPTH_TYPE.lower())
                            break

            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str:
                    logger.warning(
                        "%s WebSocket rate limited, backing off", self.DEPTH_TYPE.lower()
                    )
                    self._admission.record_rate_limit_cooldown()
                else:
                    logger.error("%s_connection_error: %s", self.DEPTH_TYPE.lower(), exc)
                with self._lock:
                    self._is_connected = False
                    self._ws = None
                    self._reconnect_count += 1

            if not self._stop_event.is_set():
                wait_time = min(backoff, max_backoff)
                logger.info("%s_reconnecting in %.1fs", self.DEPTH_TYPE.lower(), wait_time)
                await asyncio.sleep(wait_time)
                backoff = min(backoff * 2, max_backoff)

    def _send_subscription(self, instruments: list[tuple[str, str]]) -> None:
        """Send subscription JSON message over the live WebSocket."""
        subscription_msg = {
            "RequestCode": self.REQUEST_CODE,
            "InstrumentCount": len(instruments),
            "InstrumentList": [
                {
                    "ExchangeSegment": exchange,
                    "SecurityId": security_id,
                }
                for exchange, security_id in instruments
            ],
        }
        payload = json.dumps(subscription_msg)

        logger.debug(
            "%s_subscription_sending",
            self.DEPTH_TYPE.lower(),
            extra={"count": len(instruments)},
        )

        if not self._ws:
            self._dropped_depths += 1
            logger.warning("%s_subscription_dropped_no_ws", self.DEPTH_TYPE.lower())
            return

        # Subscriptions from gateway threads must use the feed's dedicated loop,
        # not asyncio.get_running_loop() on the caller thread.
        loop = self._ws_loop
        if loop is None or not loop.is_running():
            self._dropped_depths += 1
            logger.warning(
                "%s_subscription_dropped_no_ws_loop",
                self.DEPTH_TYPE.lower(),
            )
            return

        # run_coroutine_threadsafe returns a concurrent.futures.Future.
        # We register a done-callback so failures increment the dropped
        # counter instead of vanishing.
        future = asyncio.run_coroutine_threadsafe(self._ws.send(payload), loop)

        def _on_send_done(fut) -> None:
            try:
                fut.result()
            except Exception as exc:
                self._dropped_depths += 1
                logger.error(
                    "%s_subscription_send_failed: %s",
                    self.DEPTH_TYPE.lower(),
                    exc,
                )

        future.add_done_callback(_on_send_done)

    def _close_active_websocket(
        self,
        ws: Any,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Close the live socket from a synchronous caller."""
        close = getattr(ws, "close", None)
        if not callable(close):
            return
        try:
            if loop is not None and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(close(), loop)
                future.result(timeout=2.0)
                return
            result = close()
            if asyncio.iscoroutine(result):
                logger.debug(
                    "%s_auth_reconnect_close_skipped_no_loop",
                    self.DEPTH_TYPE.lower(),
                )
        except Exception as exc:
            logger.debug(
                "%s_auth_reconnect_close_failed: %s",
                self.DEPTH_TYPE.lower(),
                exc,
            )

    def update_token(self, new_token: str) -> None:
        """Token-refresh hook: updates cached token and triggers reconnect."""
        if not new_token or new_token == self._access_token:
            return
        self._access_token = new_token
        self.request_auth_reconnect()

    def request_auth_reconnect(self) -> None:
        """Close the active WebSocket so ``_websocket_loop`` reconnects with fresh auth."""
        with self._lock:
            ws = self._ws
            loop = self._ws_loop
        if ws is None:
            return
        self._close_active_websocket(ws, loop=loop)
