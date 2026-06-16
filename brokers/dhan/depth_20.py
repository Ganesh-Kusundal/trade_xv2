"""20-level market depth WebSocket feed for Dhan.

Implements ManagedService protocol for lifecycle management.
Endpoint: wss://depth-api-feed.dhan.co/twentydepth
Max instruments: 50 per connection
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from brokers.common.core.models import DepthLevel, MarketDepth
from brokers.common.event_bus import DomainEvent, EventBus
from brokers.common.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
)

logger = logging.getLogger(__name__)


class DhanDepth20Feed(ManagedService):
    """20-level market depth via WebSocket.
    
    Dhan API provides 20-level depth on a separate WebSocket endpoint.
    This feed manages subscriptions (max 50 instruments) and parses
    binary depth packets.
    
    Endpoint: wss://depth-api-feed.dhan.co/twentydepth
    Max instruments: 50 per connection
    Request code: 23
    """
    
    name = "dhan.depth_20"
    
    ENDPOINT = "wss://depth-api-feed.dhan.co/twentydepth"
    MAX_INSTRUMENTS = 50
    REQUEST_CODE = 23  # Full Market Depth
    
    # Binary packet constants
    HEADER_SIZE = 12
    DEPTH_LEVEL_SIZE = 16  # 8 bytes price + 4 bytes quantity + 4 bytes orders
    TOTAL_DEPTH_PACKETS = 20
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51
    
    def __init__(
        self,
        client_id: str,
        access_token: str,
        instruments: list[tuple[str, str]] | None = None,
        event_bus: EventBus | None = None,
    ):
        """
        Args:
            client_id: Dhan client ID
            access_token: Dhan access token
            instruments: List of (exchange_segment, security_id) tuples
            event_bus: Optional event bus for publishing depth events
        """
        self._client_id = client_id
        self._access_token = access_token
        self._instruments = instruments or []
        self._event_bus = event_bus
        
        self._subscriptions: list[tuple[str, str]] = list(self._instruments)
        self._depth_callbacks: list[Callable[[MarketDepth], None]] = []

        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_connected = False
        self._reconnect_count = 0
        self._last_message_at: datetime | None = None
        self._lock = threading.Lock()

        # Per-security_id depth cache.  Each entry holds the last-seen bids
        # and asks independently so that a one-sided packet never zeros out
        # the other side.
        self._depth_cache: dict[int, dict[str, list[DepthLevel]]] = {}
        self._depth_cache_lock = threading.Lock()
        
        # Validate instrument count
        if len(self._subscriptions) > self.MAX_INSTRUMENTS:
            raise ValueError(
                f"Maximum {self.MAX_INSTRUMENTS} instruments allowed for 20-level depth, "
                f"got {len(self._subscriptions)}"
            )
    
    @property
    def max_instruments(self) -> int:
        """Maximum number of instruments allowed per connection."""
        return self.MAX_INSTRUMENTS
    
    def on_depth(self, callback: "Callable[[MarketDepth], None]") -> None:
        """Register a callback for depth updates.

        The callback receives a :class:`~brokers.common.core.models.MarketDepth`
        with up to 20 bid and 20 ask levels.
        """
        self._depth_callbacks.append(callback)

    def latest_depth(self, security_id: int) -> MarketDepth | None:
        """Return the most-recent cached :class:`MarketDepth` for *security_id*.

        Returns ``None`` if no packet has been received yet for that security.
        """
        with self._depth_cache_lock:
            entry = self._depth_cache.get(security_id)
        if entry is None:
            return None
        return MarketDepth(
            bids=list(entry.get("bids", [])),
            asks=list(entry.get("asks", [])),
            depth_type="DEPTH_20",
        )
    
    def subscribe(self, instruments: list[tuple[str, str]]) -> None:
        """Subscribe to additional instruments.
        
        Args:
            instruments: List of (exchange_segment, security_id) tuples
            
        Raises:
            ValueError: If total subscriptions exceed MAX_INSTRUMENTS
        """
        total = len(self._subscriptions) + len(instruments)
        if total > self.MAX_INSTRUMENTS:
            raise ValueError(
                f"Maximum {self.MAX_INSTRUMENTS} instruments allowed for 20-level depth, "
                f"would have {total}"
            )
        
        self._subscriptions.extend(instruments)
        logger.info("depth_20_subscribe", extra={
            "count": len(instruments),
            "total": len(self._subscriptions),
        })
        
        # Send subscription message if connected
        if self._is_connected and self._ws:
            self._send_subscription(instruments)
    
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
        logger.info("depth_20_started")
    
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
                logger.warning("Error closing depth_20 WebSocket: %s", exc)
        
        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning(
                    "dhan.depth_20 thread did not stop within %ss", timeout_seconds
                )
        
        logger.info("depth_20_stopped")
    
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
                "subscriptions": len(self._subscriptions),
                "last_message_age_seconds": last_message_age if last_message_age is not None else -1,
            },
        )
    
    def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        while not self._stop_event.is_set():
            try:
                self._connect_and_run()
            except Exception as exc:
                logger.error("depth_20_error: %s", exc)
            
            if not self._stop_event.is_set():
                self._reconnect_count += 1
                time.sleep(min(2 ** min(self._reconnect_count, 5), 30))
    
    def _connect_and_run(self) -> None:
        """Establish WebSocket connection and process messages."""
        try:
            import asyncio
            import websockets
        except ImportError:
            logger.error("websockets package not installed: pip install websockets")
            return
        
        url = f"{self.ENDPOINT}?token={self._access_token}&clientId={self._client_id}&authType=2"
        
        logger.info("depth_20_connecting", extra={"endpoint": self.ENDPOINT})
        
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
                    
                    logger.info("depth_20_connected")
                    
                    # Send initial subscriptions
                    if self._subscriptions:
                        self._send_subscription(self._subscriptions)
                    
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
                            logger.warning("depth_20_connection_closed")
                            break
            
            except Exception as exc:
                logger.error("depth_20_connection_error: %s", exc)
                with self._lock:
                    self._is_connected = False
                    self._ws = None
                    self._reconnect_count += 1
            
            # Backoff before reconnect
            if not self._stop_event.is_set():
                wait_time = min(backoff, max_backoff)
                logger.info("depth_20_reconnecting in %.1fs", wait_time)
                await asyncio.sleep(wait_time)
                backoff = min(backoff * 2, max_backoff)
    
    def _send_subscription(self, instruments: list[tuple[str, str]]) -> None:
        """Send subscription JSON message over the live WebSocket.

        Always called from inside ``_websocket_handler`` (an async coroutine),
        so ``asyncio.get_running_loop()`` is always safe here.
        """
        import asyncio
        import json

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

        logger.debug("depth_20_subscription_sent", extra={"count": len(instruments)})

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
                logger.warning("depth_20_packet_too_short: %d bytes", len(data))
                return

            # Parse header
            response_code = data[2]
            security_id   = struct.unpack_from('<I', data, 4)[0]

            self._last_message_at = datetime.now(timezone.utc)

            # Only process bid/ask depth packets
            if response_code in (self.BID_RESPONSE_CODE, self.ASK_RESPONSE_CODE):
                depth_data = self._parse_depth_packet(data, response_code, security_id)
                self._dispatch_depth(depth_data)

        except Exception as exc:
            logger.error("depth_20_parse_error: %s", exc, exc_info=True)
    
    def _parse_depth_packet(self, data: bytes, response_code: int, security_id: int) -> dict:
        """Parse 20-level depth binary packet.

        Packet structure:
        - 12 bytes header
        - 320 bytes depth data (20 levels × 16 bytes each)

        Each level (16 bytes):
        - 8 bytes: price (float64 little-endian)
        - 4 bytes: quantity (uint32 little-endian)
        - 4 bytes: orders  (uint32 little-endian)
        """
        depth_levels = []

        for i in range(self.TOTAL_DEPTH_PACKETS):
            offset = self.HEADER_SIZE + (i * self.DEPTH_LEVEL_SIZE)
            if offset + self.DEPTH_LEVEL_SIZE > len(data):
                break
            price    = struct.unpack_from('<d', data, offset)[0]
            quantity = struct.unpack_from('<I', data, offset + 8)[0]
            orders   = struct.unpack_from('<I', data, offset + 12)[0]
            if quantity > 0:  # skip empty levels
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
            "security_id": security_id,
        }
    
    def _dispatch_depth(self, depth_data: dict) -> None:
        """Update the depth cache and dispatch to callbacks / event bus.

        Dhan sends bid and ask packets *separately* (response_code 41 vs 51).
        We merge both sides in ``_depth_cache`` keyed by the binary security_id
        so callers always see a complete picture.
        """
        side   = depth_data["side"]    # "bids" or "asks"
        levels = depth_data["levels"]  # list[DepthLevel]
        sec_id = depth_data.get("security_id", 0)

        # Update the cache for this side only — leave the other side intact.
        with self._depth_cache_lock:
            entry = self._depth_cache.setdefault(sec_id, {"bids": [], "asks": []})
            entry[side] = levels
            merged = MarketDepth(
                bids=list(entry["bids"]),
                asks=list(entry["asks"]),
                depth_type="DEPTH_20",
                timestamp=datetime.now(timezone.utc),
            )

        # Fire registered callbacks with the canonical MarketDepth.
        for callback in self._depth_callbacks:
            try:
                callback(merged)
            except Exception as exc:
                logger.error("depth_20_callback_error: %s", exc)

        # Publish to event bus.
        if self._event_bus:
            try:
                self._event_bus.publish(
                    DomainEvent.now(
                        "DEPTH_20",
                        {"depth": merged, "depth_type": "DEPTH_20"},
                        source="DhanDepth20Feed",
                    )
                )
            except Exception as exc:
                logger.error("depth_20_event_bus_error: %s", exc)
