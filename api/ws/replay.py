"""WebSocket handlers for replay market data."""

from __future__ import annotations

import asyncio
import json
import logging

import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth import reject_ws_if_unauthorized

logger = logging.getLogger(__name__)

router = APIRouter()

_stream_tasks: dict[str, asyncio.Task] = {}


class ReplayConnectionManager:
    """Manage WebSocket connections for replay streams."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.session_map: dict[str, str] = {}

    async def connect(self, websocket: WebSocket, connection_id: str, session_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.session_map[connection_id] = session_id
        logger.info("Replay WS connected: %s -> session %s", connection_id, session_id)

    async def disconnect(self, connection_id: str):
        task = _stream_tasks.pop(connection_id, None)
        if task is not None:
            task.cancel()
        self.active_connections.pop(connection_id, None)
        self.session_map.pop(connection_id, None)
        logger.info("Replay WS disconnected: %s", connection_id)

    async def send_to_client(self, connection_id: str, message: dict):
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(message)
            except Exception as exc:
                logger.error("Failed to send to %s: %s", connection_id, exc)


replay_manager = ReplayConnectionManager()


def _cancel_stream(connection_id: str) -> None:
    task = _stream_tasks.pop(connection_id, None)
    if task is not None:
        task.cancel()


async def _stream_replay_candles(
    connection_id: str,
    session_id: str,
    *,
    speed: float = 1.0,
    seek_ts: int | None = None,
) -> None:
    from api.routers.replay import get_replay_session_store
    from datalake.gateway import DataLakeGateway

    store = get_replay_session_store()
    session = store.get(session_id)
    if session is None:
        await replay_manager.send_to_client(
            connection_id,
            {
                "type": "error",
                "code": "SESSION_NOT_FOUND",
                "message": f"Unknown session {session_id}",
            },
        )
        return

    symbol = session.get("symbol") or (session.get("universe") or "RELIANCE")
    date = session.get("date") or ""
    timeframe = session.get("timeframe") or "1m"
    speed = float(session.get("speed") or speed or 1.0)

    gateway = DataLakeGateway(root="market_data")
    df = gateway.history(symbol, timeframe=timeframe, from_date=date, to_date=date)
    if df.empty:
        await replay_manager.send_to_client(
            connection_id,
            {"type": "error", "code": "NO_DATA", "message": f"No candles for {symbol} on {date}"},
        )
        return

    ts_col = "timestamp" if "timestamp" in df.columns else "date" if "date" in df.columns else None
    if ts_col is None:
        await replay_manager.send_to_client(
            connection_id,
            {"type": "error", "code": "BAD_DATA", "message": "Missing timestamp column"},
        )
        return

    df = df.sort_values(ts_col).reset_index(drop=True)
    ms_per_candle = max(0.02, 0.2 / max(speed, 0.25))

    try:
        for _, row in df.iterrows():
            ts = pd.Timestamp(row[ts_col])
            t_ms = int(ts.timestamp() * 1000)
            if seek_ts is not None and t_ms < seek_ts:
                continue
            candle = {
                "t": t_ms,
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
                "v": float(row.get("volume", 0)),
            }
            await replay_manager.send_to_client(
                connection_id,
                {"type": "replay_candle", "session_id": session_id, "candle": candle},
            )
            await replay_manager.send_to_client(
                connection_id,
                {
                    "type": "replay_state",
                    "session_id": session_id,
                    "state": "PLAYING",
                    "speed": speed,
                    "cursor_t": t_ms,
                },
            )
            await asyncio.sleep(ms_per_candle)
    except asyncio.CancelledError:
        await replay_manager.send_to_client(
            connection_id,
            {"type": "replay_state", "session_id": session_id, "state": "PAUSED", "speed": speed},
        )
        raise

    await replay_manager.send_to_client(
        connection_id,
        {
            "type": "replay_state",
            "session_id": session_id,
            "state": "ENDED",
            "speed": speed,
            "cursor_t": t_ms,
        },
    )


def _start_stream(
    connection_id: str, session_id: str, *, speed: float = 1.0, seek_ts: int | None = None
) -> None:
    _cancel_stream(connection_id)
    _stream_tasks[connection_id] = asyncio.create_task(
        _stream_replay_candles(connection_id, session_id, speed=speed, seek_ts=seek_ts)
    )


@router.websocket("/replay/{session_id}")
async def replay_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for replay market data stream."""
    import uuid

    connection_id = str(uuid.uuid4())

    if not await reject_ws_if_unauthorized(websocket):
        return

    await replay_manager.connect(websocket, connection_id, session_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            action = message.get("action")

            if action == "play":
                speed = float(message.get("speed", 1))
                _start_stream(connection_id, session_id, speed=speed)
                await replay_manager.send_to_client(
                    connection_id,
                    {
                        "type": "replay_state",
                        "session_id": session_id,
                        "state": "PLAYING",
                        "speed": speed,
                    },
                )

            elif action == "pause":
                _cancel_stream(connection_id)
                await replay_manager.send_to_client(
                    connection_id,
                    {"type": "replay_state", "session_id": session_id, "state": "PAUSED"},
                )

            elif action == "stop":
                _cancel_stream(connection_id)
                await replay_manager.send_to_client(
                    connection_id,
                    {"type": "replay_state", "session_id": session_id, "state": "STOPPED"},
                )

            elif action == "seek":
                timestamp = message.get("timestamp") or message.get("to_t")
                seek_ts = int(timestamp) if timestamp is not None else None
                speed = float(message.get("speed", 1))
                _start_stream(connection_id, session_id, speed=speed, seek_ts=seek_ts)

            elif action == "speed":
                speed = float(message.get("speed", 1))
                from api.routers.replay import get_replay_session_store

                get_replay_session_store().update(session_id, speed=speed)

            elif action == "ping":
                await replay_manager.send_to_client(
                    connection_id,
                    {"type": "pong", "timestamp": message.get("timestamp")},
                )

    except WebSocketDisconnect:
        await replay_manager.disconnect(connection_id)
    except Exception as exc:
        logger.error("Replay WS error for %s/%s: %s", connection_id, session_id, exc)
        await replay_manager.disconnect(connection_id)
