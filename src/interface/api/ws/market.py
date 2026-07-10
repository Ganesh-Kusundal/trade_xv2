"""WebSocket handlers for real-time market data."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from interface.api.auth import reject_ws_if_unauthorized

logger = logging.getLogger(__name__)

router = APIRouter()

# P1-5: Maximum number of pending messages per WebSocket connection.
# If the queue is full, the oldest message is dropped to prevent
# slow clients from blocking the event loop.
_WS_QUEUE_MAXSIZE = 256


# Connection manager for market data subscriptions
class MarketConnectionManager:
    """Manage WebSocket connections for market data streams.

    P1-5 fix: Added per-connection asyncio.Queue for backpressure.
    Slow clients that can't keep up with the feed will have their
    oldest messages dropped rather than blocking the event loop.
    """

    def __init__(self, max_connections: int = 500):
        self.active_connections: dict[str, WebSocket] = {}
        self.subscriptions: dict[str, set[str]] = {}  # connection_id -> symbols
        self._symbol_index: dict[str, set[str]] = {}  # symbol -> connection_ids (reverse index)
        self._wildcard_connections: set[str] = set()  # connections with empty subscription (get all events)
        self._send_queues: dict[str, asyncio.Queue] = {}  # connection_id -> message queue
        self._send_tasks: dict[str, asyncio.Task] = {}  # connection_id -> sender task
        self._seq_counters: dict[str, int] = {}  # connection_id -> sequence number
        self._max_connections = max_connections

    async def connect(self, websocket: WebSocket, connection_id: str):
        if len(self.active_connections) >= self._max_connections:
            await websocket.close(code=1013, reason="Too many connections")
            logger.warning("Rejected WS connection %s: max connections reached", connection_id)
            return
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.subscriptions[connection_id] = set()
        self._wildcard_connections.add(connection_id)
        self._send_queues[connection_id] = asyncio.Queue(maxsize=_WS_QUEUE_MAXSIZE)
        self._seq_counters[connection_id] = 0
        # Start background sender task for this connection
        self._send_tasks[connection_id] = asyncio.create_task(
            self._send_loop(connection_id), name=f"ws-sender-{connection_id}"
        )
        logger.info("Market WS connected: %s", connection_id)

    async def disconnect(self, connection_id: str):
        symbols = self.subscriptions.pop(connection_id, None)
        self.active_connections.pop(connection_id, None)
        self._wildcard_connections.discard(connection_id)
        if symbols:
            for sym in symbols:
                idx = self._symbol_index.get(sym)
                if idx is not None:
                    idx.discard(connection_id)
                    if not idx:
                        del self._symbol_index[sym]
        # Cancel and clean up sender task
        task = self._send_tasks.pop(connection_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._send_queues.pop(connection_id, None)
        self._seq_counters.pop(connection_id, None)
        if symbols:
            from interface.api.ws.feed_wiring import unsubscribe_symbols_from_broker

            unsubscribe_symbols_from_broker(list(symbols))
        logger.info("Market WS disconnected: %s", connection_id)

    async def _send_loop(self, connection_id: str) -> None:
        """Background task that drains the message queue to the WebSocket.

        P1-5: Decouples message production from consumption. If the client
        is slow, the queue fills up and old messages are dropped (via
        put_nowait with overflow handling) rather than blocking producers.
        """
        queue = self._send_queues.get(connection_id)
        ws = self.active_connections.get(connection_id)
        if queue is None or ws is None:
            return
        try:
            while True:
                message = await queue.get()
                if message is None:
                    break  # Poison pill — shutdown signal
                try:
                    await ws.send_json(message)
                except Exception as exc:
                    logger.debug("WS send failed for %s: %s", connection_id, exc)
                    task = asyncio.ensure_future(self.disconnect(connection_id))
                    task.add_done_callback(lambda _: None)
                    break
        except asyncio.CancelledError:
            pass

    async def subscribe(self, connection_id: str, symbols: list[str]):
        if connection_id in self.subscriptions:
            self.subscriptions[connection_id].update(symbols)
            self._wildcard_connections.discard(connection_id)
            for sym in symbols:
                self._symbol_index.setdefault(sym, set()).add(connection_id)
            logger.info("Market WS %s subscribed to: %s", connection_id, symbols)

    async def unsubscribe(self, connection_id: str, symbols: list[str]):
        if connection_id in self.subscriptions:
            sub = self.subscriptions[connection_id]
            for symbol in symbols:
                sub.discard(symbol)
                idx = self._symbol_index.get(symbol)
                if idx is not None:
                    idx.discard(connection_id)
                    if not idx:
                        del self._symbol_index[symbol]
            if not sub:
                self._wildcard_connections.add(connection_id)

    async def send_to_client(self, connection_id: str, message: dict):
        """Enqueue a message for sending with sequence number.

        Non-blocking with overflow drop. Adds monotonic _seq field
        so clients can detect gaps from dropped messages.
        """
        queue = self._send_queues.get(connection_id)
        if queue is None:
            return
        # Add sequence number for gap detection
        seq = self._seq_counters.get(connection_id, 0)
        message["_seq"] = seq
        self._seq_counters[connection_id] = seq + 1
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # P1-5: Drop oldest message to make room (backpressure)
            try:
                queue.get_nowait()  # Drop oldest
                queue.put_nowait(message)
                logger.debug("WS queue full for %s — dropped oldest message", connection_id)
            except asyncio.QueueEmpty:
                pass

    def targets_for_symbol(self, symbol: str | None) -> set[str]:
        """Return connection IDs that should receive events for *symbol*.

        Includes wildcard connections (empty subscription list) plus any
        connections explicitly subscribed to *symbol*.
        """
        targets: set[str] = set(self._wildcard_connections)
        if symbol and symbol in self._symbol_index:
            targets.update(self._symbol_index[symbol])
        return targets


market_manager = MarketConnectionManager()


@router.websocket("/market")
async def market_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time market data.

    Message protocol:
    - Client -> Server: {"action": "subscribe", "symbols": ["RELIANCE", "TCS"]}
    - Client -> Server: {"action": "unsubscribe", "symbols": ["RELIANCE"]}
    - Server -> Client: {"type": "quote", "symbol": "RELIANCE", "ltp": 2450.50, ...}
    - Server -> Client: {"type": "candle", "symbol": "RELIANCE", "timeframe": "1m", ...}
    """
    connection_id = str(uuid.uuid4())

    if not await reject_ws_if_unauthorized(websocket):
        return

    await market_manager.connect(websocket, connection_id)

    # Check if event_bus is available — fail loud if not
    from interface.api.deps import get_event_bus

    event_bus = get_event_bus()
    if event_bus is None:
        await market_manager.send_to_client(
            connection_id,
            {
                "type": "error",
                "reason": "no_feed_source",
                "message": "Market data feed not connected",
            },
        )
        await websocket.close(code=1013, reason="Market feed unavailable")
        return

    try:
        while True:
            # Wait for client messages
            data = await websocket.receive_text()
            message = json.loads(data)

            action = message.get("action")

            if action == "subscribe":
                # Check if event_bus is available before allowing subscribe
                from interface.api.deps import get_event_bus

                event_bus = get_event_bus()
                if event_bus is None:
                    await market_manager.send_to_client(
                        connection_id,
                        {
                            "type": "error",
                            "reason": "feed_unavailable",
                            "message": "Market data feed not connected",
                        },
                    )
                    continue

                symbols = message.get("symbols", [])
                await market_manager.subscribe(connection_id, symbols)
                from interface.api.ws.feed_wiring import subscribe_symbols_to_broker

                subscribe_symbols_to_broker(symbols)
                await market_manager.send_to_client(
                    connection_id,
                    {"type": "subscribed", "symbols": symbols},
                )

            elif action == "unsubscribe":
                symbols = message.get("symbols", [])
                await market_manager.unsubscribe(connection_id, symbols)
                from interface.api.ws.feed_wiring import unsubscribe_symbols_from_broker

                unsubscribe_symbols_from_broker(symbols)
                await market_manager.send_to_client(
                    connection_id,
                    {"type": "unsubscribed", "symbols": symbols},
                )

            elif action == "ping":
                await market_manager.send_to_client(
                    connection_id,
                    {"type": "pong", "timestamp": message.get("timestamp")},
                )

    except WebSocketDisconnect:
        await market_manager.disconnect(connection_id)
    except Exception as exc:
        logger.error("Market WS error for %s: %s", connection_id, exc)
        await market_manager.disconnect(connection_id)


@router.websocket("/market/{symbol}")
async def symbol_websocket(websocket: WebSocket, symbol: str):
    """WebSocket endpoint for single symbol market data.

    Simplified endpoint for clients that only need one symbol.
    Automatically subscribes to the symbol in the path.
    """
    connection_id = str(uuid.uuid4())

    if not await reject_ws_if_unauthorized(websocket):
        return

    await market_manager.connect(websocket, connection_id)
    await market_manager.subscribe(connection_id, [symbol])
    from interface.api.ws.feed_wiring import subscribe_symbols_to_broker

    subscribe_symbols_to_broker([symbol])

    try:
        while True:
            # Keep connection alive, stream data automatically
            await websocket.receive_text()

    except WebSocketDisconnect:
        await market_manager.disconnect(connection_id)
    except Exception as exc:
        logger.error("Symbol WS error for %s/%s: %s", connection_id, symbol, exc)
        await market_manager.disconnect(connection_id)
