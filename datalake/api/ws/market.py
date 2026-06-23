"""WebSocket handlers for real-time market data."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from datalake.api.auth import reject_ws_if_unauthorized

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection manager for market data subscriptions
class MarketConnectionManager:
    """Manage WebSocket connections for market data streams."""
    
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.subscriptions: dict[str, list[str]] = {}  # connection_id -> symbols
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.subscriptions[connection_id] = []
        logger.info("Market WS connected: %s", connection_id)
    
    async def disconnect(self, connection_id: str):
        self.active_connections.pop(connection_id, None)
        self.subscriptions.pop(connection_id, None)
        logger.info("Market WS disconnected: %s", connection_id)
    
    async def subscribe(self, connection_id: str, symbols: list[str]):
        if connection_id in self.subscriptions:
            self.subscriptions[connection_id].extend(symbols)
            logger.info("Market WS %s subscribed to: %s", connection_id, symbols)
    
    async def unsubscribe(self, connection_id: str, symbols: list[str]):
        if connection_id in self.subscriptions:
            for symbol in symbols:
                if symbol in self.subscriptions[connection_id]:
                    self.subscriptions[connection_id].remove(symbol)
    
    async def send_to_client(self, connection_id: str, message: dict):
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(message)
            except Exception as exc:
                logger.error("Failed to send to %s: %s", connection_id, exc)

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
    import uuid
    connection_id = str(uuid.uuid4())

    if not await reject_ws_if_unauthorized(websocket):
        return

    await market_manager.connect(websocket, connection_id)
    
    # Check if event_bus is available — fail loud if not
    from datalake.api.deps import get_event_bus
    event_bus = get_event_bus()
    if event_bus is None:
        await market_manager.send_to_client(
            connection_id,
            {"type": "error", "reason": "no_feed_source", "message": "Market data feed not connected"},
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
                from datalake.api.deps import get_event_bus
                event_bus = get_event_bus()
                if event_bus is None:
                    await market_manager.send_to_client(
                        connection_id,
                        {"type": "error", "reason": "feed_unavailable", "message": "Market data feed not connected"},
                    )
                    continue
                
                symbols = message.get("symbols", [])
                await market_manager.subscribe(connection_id, symbols)
                from datalake.api.ws.feed_wiring import subscribe_symbols_to_broker
                subscribe_symbols_to_broker(symbols)
                await market_manager.send_to_client(
                    connection_id,
                    {"type": "subscribed", "symbols": symbols},
                )
            
            elif action == "unsubscribe":
                symbols = message.get("symbols", [])
                await market_manager.unsubscribe(connection_id, symbols)
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
    import uuid
    connection_id = str(uuid.uuid4())

    if not await reject_ws_if_unauthorized(websocket):
        return

    await market_manager.connect(websocket, connection_id)
    await market_manager.subscribe(connection_id, [symbol])
    from datalake.api.ws.feed_wiring import subscribe_symbols_to_broker
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
