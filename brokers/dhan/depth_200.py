"""200-level market depth WebSocket feed for Dhan.

Implements ManagedService protocol for lifecycle management.
Endpoint: wss://full-depth-api.dhan.co/twohundreddepth (see ``config.endpoints.Dhan.WS_DEPTH_200``)
Max instruments: 1 per connection (Dhan API limitation)
"""

from __future__ import annotations

import asyncio
import logging
import struct
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from config.endpoints import Dhan as _DhanEndpoints

from brokers.common.core.domain import DepthLevel, MarketDepth
from brokers.common.event_bus import DomainEvent, EventBus
from brokers.common.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
)

logger = logging.getLogger(__name__)


class DhanDepth200Feed(ManagedService):
    """200-level market depth via WebSocket.

    Dhan API provides 200-level depth on a separate WebSocket endpoint.
    CRITICAL LIMITATION: Only 1 instrument per connection allowed.

    Endpoint: wss://full-depth-api.dhan.co/twohundreddepth
    Max instruments: 1 per connection
    Request code: 23
    """

    name = "dhan.depth_200"

    ENDPOINT = _DhanEndpoints.WS_DEPTH_200
    MAX_INSTRUMENTS = 1
    REQUEST_CODE = 23  # Full Market Depth

    # Binary packet constants
    HEADER_SIZE = 12
    DEPTH_LEVEL_SIZE = 16  # 8 bytes price + 4 bytes quantity + 4 bytes orders
    TOTAL_DEPTH_PACKETS = 200
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

    def __init__(
        self,
        client_id: str,
        access_token: str,
        instrument: tuple[str, str] | None = None,
        event_bus: EventBus | None = None,
    ):
        """
        Args:
            client_id: Dhan client ID
            access_token: Dhan access token
            instrument: Single (exchange_segment, security_id) tuple
            event_bus: Optional event bus for publishing depth events
        """
        self._client_id = client_id
        self._access_token = access_token
        self._instrument = instrument
        self._event_bus = event_bus

        self._subscriptions: list[tuple[str, str]] = [instrument] if instrument else []
        self._depth_callbacks: list[Callable[[MarketDepth], None]] = []
        self._callback_lock = threading.Lock()

        self._ws = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._is_connected = False
        self._reconnect_count = 0
        self._last_message_at: datetime | None = None
        self._lock = threading.Lock()

        # Single-instrument depth cache (bids + asks stored independently).
        self._depth_cache: dict[str, list[DepthLevel]] = {"bids": [], "asks": []}
        self._depth_cache_lock = threading.Lock()

        # Validate: only 1 instrument allowed
        if len(self._subscriptions) > self.MAX_INSTRUMENTS:
            raise ValueError(
                f"Maximum {self.MAX_INSTRUMENTS} instrument allowed for 200-level depth, "
                f"got {len(self._subscriptions)}"
            )

    @property
    def max_instruments(self) -> int:
        """Maximum number of instruments allowed per connection."""
        return self.MAX_INSTRUMENTS

    @property
    def subscriptions(self) -> list[tuple[str, str]]:
        """Return a copy of the current subscription list."""
        return list(self._subscriptions)

    @property
    def is_running(self) -> bool:
        """Whether the feed thread is alive (started and not stopped)."""
        return bool(self._thread and self._thread.is_alive())

    def on_depth(self, callback: Callable[[MarketDepth], None]) -> None:
        """Register a callback for depth updates.

        The callback receives a :class:`~brokers.common.core.domain.MarketDepth`
        with up to 200 bid and 200 ask levels.
        """
        with self._callback_lock:
            self._depth_callbacks.append(callback)

    def latest_depth(self) -> MarketDepth | None:
        """Return the most-recent cached :class:`MarketDepth`.

        Returns ``None`` if no packet has been received yet.
        """
        with self._depth_cache_lock:
            bids = list(self._depth_cache["bids"])
            asks = list(self._depth_cache["asks"])
        if not bids and not asks:
            return None
        return MarketDepth(bids=bids, asks=asks, depth_type="DEPTH_200")

    def subscribe(self, instrument: tuple[str, str]) -> None:
        """Subscribe to a single instrument.

        Args:
            instrument: Single (exchange_segment, security_id) tuple

        Raises:
            ValueError: If already subscribed to an instrument
        """
        if len(self._subscriptions) >= self.MAX_INSTRUMENTS:
            raise ValueError(
                f"Only {self.MAX_INSTRUMENTS} instrument allowed for 200-level depth. "
                f"Already subscribed to {self._subscriptions[0] if self._subscriptions else 'none'}"
            )

        self._subscriptions.append(instrument)
        self._instrument = instrument
        logger.info("depth_200_subscribe", extra={"instrument": instrument})

        # Send subscription message if connected
        if self._is_connected and self._ws:
            self._send_subscription(instrument)

    def connect(self) -> None:
        """Deprecated alias for :meth:`start`."""
        self.start()

    def start(self) -> None:
        """ManagedService protocol: start the WebSocket connection.

        Idempotent — re-calling while the thread is alive is a no-op.
        """
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._websocket_loop,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        logger.info("depth_200_started")

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
            try:
                ws.close()
            except Exception as exc:
                logger.warning("Error closing depth_200 WebSocket: %s", exc)

        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning(
                    "dhan.depth_200 thread did not stop within %ss", timeout_seconds
                )

        logger.info("depth_200_stopped")

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = self._is_connected
            reconnect_count = self._reconnect_count
            last_message_age = (
                (datetime.now(timezone.utc) - self._last_message_at).total_seconds()
                if self._last_message_at is not None
                else None
            )

        if thread_alive and is_connected:
            state = HealthState.HEALTHY
            detail = "running and connected"
        elif thread_alive and not is_connected:
            state = HealthState.DEGRADED
            detail = "thread running but not connected (reconnecting?)"
        else:
            state = HealthState.STOPPED
            detail = "not started"

        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
            detail=detail,
            metrics={
                "reconnect_count": reconnect_count,
                "subscribed_instrument": self._subscriptions[0] if self._subscriptions else None,
                "last_message_age_seconds": last_message_age if last_message_age is not None else -1,
            },
        )

    def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        while not self._stop_event.is_set():
            try:
                self._connect_and_run()
            except Exception as exc:
                logger.error("depth_200_error: %s", exc)

            if not self._stop_event.is_set():
                self._reconnect_count += 1
                time.sleep(min(2 ** min(self._reconnect_count, 5), 30))

    def _connect_and_run(self) -> None:
        """Establish WebSocket connection and process messages."""
        import importlib.util

        if importlib.util.find_spec("websockets") is None:
            logger.error("websockets package not installed: pip install websockets")
            return
        import asyncio

        url = f"{self.ENDPOINT}?token={self._access_token}&clientId={self._client_id}&authType=2"

        logger.info("depth_200_connecting", extra={"endpoint": self.ENDPOINT})

        # Run async WebSocket in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._websocket_handler(url))
        finally:
            loop.close()
            with self._lock:
                self._is_connected = False

    async def _websocket_handler(self, url: str) -> None:
        """Async WebSocket handler with auto-reconnect."""
        import websockets

        backoff = 1.0
        max_backoff = 30.0

        while not self._stop_event.is_set():
            try:
                async with websockets.connect(url) as ws:
                    with self._lock:
                        self._ws = ws
                        self._is_connected = True
                        self._reconnect_count = 0

                    logger.info("depth_200_connected")

                    # Send initial subscription (only 1 instrument allowed)
                    if self._instrument:
                        self._send_subscription(self._instrument)

                    # Process messages
                    while not self._stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(
                                ws.recv(), timeout=30.0
                            )

                            if isinstance(message, bytes):
                                self._process_binary_message(message)

                            # Reset backoff on successful message
                            backoff = 1.0

                        except asyncio.TimeoutError:
                            # Heartbeat timeout, connection still alive
                            continue

                        except websockets.ConnectionClosed:
                            logger.warning("depth_200_connection_closed")
                            break

            except Exception as exc:
                logger.error("depth_200_connection_error: %s", exc)
                with self._lock:
                    self._is_connected = False
                    self._ws = None
                    self._reconnect_count += 1

            # Backoff before reconnect
            if not self._stop_event.is_set():
                wait_time = min(backoff, max_backoff)
                logger.info("depth_200_reconnecting in %.1fs", wait_time)
                await asyncio.sleep(wait_time)
                backoff = min(backoff * 2, max_backoff)

    def _send_subscription(self, instrument: tuple[str, str]) -> None:
        """Send subscription JSON message over the live WebSocket.

        Always called from inside ``_websocket_handler`` (an async coroutine),
        so ``asyncio.get_running_loop()`` is always safe here.
        """
        import asyncio
        import json

        exchange, security_id = instrument
        subscription_msg = {
            "RequestCode": self.REQUEST_CODE,
            "ExchangeSegment": exchange,
            "SecurityId": security_id,
        }

        logger.debug("depth_200_subscription_sent", extra={"instrument": instrument})

        if self._ws:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._ws.send(json.dumps(subscription_msg)))
            except RuntimeError:
                # No running loop (test context) — skip silently
                pass

    def _process_binary_message(self, data: bytes) -> None:
        """Parse binary depth packet and dispatch callbacks."""
        try:
            if len(data) < self.HEADER_SIZE:
                logger.warning("depth_200_packet_too_short: %d bytes", len(data))
                return

            # Parse header
            response_code = data[2]
            num_rows      = struct.unpack_from('<I', data, 8)[0]

            self._last_message_at = datetime.now(timezone.utc)

            # Only process bid/ask depth packets
            if response_code in (self.BID_RESPONSE_CODE, self.ASK_RESPONSE_CODE):
                depth_data = self._parse_depth_packet(data, response_code, num_rows)
                self._dispatch_depth(depth_data)

        except Exception as exc:
            logger.error("depth_200_parse_error: %s", exc, exc_info=True)

    def _parse_depth_packet(self, data: bytes, response_code: int, num_rows: int) -> dict:
        """Parse 200-level depth binary packet.

        Packet structure:
        - 12 bytes header
        - 3200 bytes depth data (200 levels × 16 bytes each)

        Each level (16 bytes):
        - 8 bytes: price (float64)
        - 4 bytes: quantity (uint32)
        - 4 bytes: orders (uint32)
        """
        depth_levels = []

        for i in range(num_rows):
            offset = self.HEADER_SIZE + (i * self.DEPTH_LEVEL_SIZE)

            if offset + self.DEPTH_LEVEL_SIZE > len(data):
                break

            price = struct.unpack_from('<d', data, offset)[0]
            quantity = struct.unpack_from('<I', data, offset + 8)[0]
            orders = struct.unpack_from('<I', data, offset + 12)[0]

            if quantity > 0:  # Only include levels with quantity
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
        }

    def _dispatch_depth(self, depth_data: dict) -> None:
        """Update the depth cache and dispatch to callbacks / event bus.

        Dhan sends bid and ask packets *separately* (response_code 41 vs 51).
        We merge both sides in ``_depth_cache`` so callers always see a
        complete picture.
        """
        side   = depth_data["side"]    # "bids" or "asks"
        levels = depth_data["levels"]  # list[DepthLevel]

        with self._depth_cache_lock:
            self._depth_cache[side] = levels
            merged = MarketDepth(
                bids=list(self._depth_cache["bids"]),
                asks=list(self._depth_cache["asks"]),
                depth_type="DEPTH_200",
                timestamp=datetime.now(timezone.utc),
            )

        # Fire registered callbacks with the canonical MarketDepth.
        with self._callback_lock:
            callbacks = list(self._depth_callbacks)
        for callback in callbacks:
            try:
                callback(merged)
            except Exception as exc:
                logger.error("depth_200_callback_error: %s", exc)

        # Publish to event bus.
        if self._event_bus:
            try:
                self._event_bus.publish(
                    DomainEvent.now(
                        "DEPTH_200",
                        {"depth": merged, "depth_type": "DEPTH_200"},
                        source="DhanDepth200Feed",
                    )
                )
            except Exception as exc:
                logger.error("depth_200_event_bus_error: %s", exc)
