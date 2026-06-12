"""Upstox V2 portfolio stream (orders / positions / holdings / GTT updates)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer

logger = logging.getLogger(__name__)

PortfolioListener = Callable[[str, dict[str, Any]], None]


class UpstoxPortfolioStream:
    """Subscribe to Upstox portfolio stream and normalise updates into
    ``OrderUpdateEvent`` / ``PositionUpdateEvent`` / ``HoldingUpdateEvent`` /
    ``GTTUpdateEvent`` domain events.
    """

    def __init__(
        self,
        authorizer: UpstoxFeedAuthorizer,
        socket_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._authorizer = authorizer
        self._socket_factory = socket_factory or _default_portfolio_factory
        self._socket: Any = None
        self._listeners: list[PortfolioListener] = []
        self._task: asyncio.Task[Any] | None = None
        self._stopped = False

    def add_listener(self, listener: PortfolioListener) -> None:
        self._listeners.append(listener)

    async def connect(self) -> None:
        url = self._authorizer.authorize_portfolio_stream()
        if not url:
            raise RuntimeError("Upstox portfolio stream authorize did not return a URL")
        self._socket = self._socket_factory(url)
        self._stopped = False
        self._task = asyncio.create_task(self._read_loop())

    async def disconnect(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._socket is not None:
            try:
                close = getattr(self._socket, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception:
                pass
            self._socket = None

    async def _read_loop(self) -> None:
        recv = getattr(self._socket, "recv", None)
        if recv is None:
            return
        while not self._stopped:
            try:
                raw = await recv() if asyncio.iscoroutinefunction(recv) else recv()
            except Exception as exc:
                logger.warning("Upstox portfolio stream recv error: %s", exc)
                break
            if not raw:
                continue
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except Exception:
                    continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            update_type = msg.get("type") or msg.get("update_type")
            payload = msg.get("data") if isinstance(msg, dict) else {}
            if not isinstance(payload, dict):
                continue
            for listener in self._listeners:
                with contextlib.suppress(Exception):
                    listener(str(update_type or "unknown"), payload)


def _default_portfolio_factory(url: str) -> Any:
    try:
        import websockets  # type: ignore

        return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**20)
    except ImportError as exc:
        raise RuntimeError(
            "websockets library is required for live Upstox portfolio stream"
        ) from exc
