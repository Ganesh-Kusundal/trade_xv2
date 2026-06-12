"""Upstox V3 market data WebSocket multiplexer.

Mirrors Trade_J ``UpstoxWebSocketMultiplexer``. Provides ``subscribe``,
``change_mode``, ``unsubscribe`` and dispatches parsed ticks to listeners.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

from brokers.upstox.websocket.feed_authorizer import (
    UpstoxFeedAuthorizer,
    build_subscribe_payload,
    encode_subscribe_payload,
)
from brokers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect
from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder
from brokers.upstox.websocket.v3_subscription_manager import (
    UpstoxV3SubscriptionLimits,
    UpstoxV3SubscriptionManager,
)

logger = logging.getLogger(__name__)

TickListener = Callable[[str, dict[str, Any]], None]


class UpstoxMarketDataV3Multiplexer:
    """Subscribe to Upstox V3 WebSocket feed and dispatch parsed ticks.

    In production this opens a real ``websockets`` connection to the
    authorized URI. In tests the connection can be replaced via the
    ``socket_factory`` constructor argument.
    """

    def __init__(
        self,
        authorizer: UpstoxFeedAuthorizer,
        decoder: UpstoxV3Decoder | None = None,
        limits: UpstoxV3SubscriptionLimits | None = None,
        auto_reconnect: UpstoxAutoReconnect | None = None,
        socket_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._authorizer = authorizer
        self._decoder = decoder or UpstoxV3Decoder()
        self._subscriptions = UpstoxV3SubscriptionManager(limits)
        self._reconnect = auto_reconnect or UpstoxAutoReconnect()
        self._socket_factory = socket_factory or _default_socket_factory
        self._socket: Any = None
        self._listeners: list[TickListener] = []
        self._subscribed: set[str] = set()
        self._task: asyncio.Task[Any] | None = None
        self._stopped = False

    @property
    def subscription_manager(self) -> UpstoxV3SubscriptionManager:
        return self._subscriptions

    def add_listener(self, listener: TickListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: TickListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def subscribe(
        self,
        instrument_keys: list[str],
        mode: str = "ltpc",
        *,
        guid: str | None = None,
    ) -> None:
        self._subscriptions.subscribe(instrument_keys, mode)
        if self._socket is not None:
            self._send_subscribe(instrument_keys, mode, guid=guid)
        self._subscribed.update(instrument_keys)

    def change_mode(
        self,
        instrument_keys: list[str],
        mode: str,
        *,
        guid: str | None = None,
    ) -> None:
        self._subscriptions.change_mode(instrument_keys, mode)
        if self._socket is not None:
            payload = build_subscribe_payload(instrument_keys, mode, guid=guid)
            self._send_raw("change_mode", payload)

    def unsubscribe(self, instrument_keys: list[str]) -> None:
        self._subscriptions.unsubscribe(instrument_keys)
        if self._socket is not None:
            payload = {
                "guid": "",
                "method": "unsub",
                "data": {"instrumentKeys": list(instrument_keys)},
            }
            self._send_raw("unsub", payload)
        for k in instrument_keys:
            self._subscribed.discard(k)

    def feed_authorize_url(self) -> str:
        return self._authorizer.authorize_market_data_v3()

    async def connect(self) -> None:
        """Open the WebSocket connection and start the read loop."""
        url = self._authorizer.authorize_market_data_v3()
        if not url:
            raise RuntimeError("Upstox V3 feed authorize did not return a URL")
        self._socket = self._socket_factory(url)
        await self._maybe_send_initial_subscriptions()
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
        self._reconnect.reset()

    async def _maybe_send_initial_subscriptions(self) -> None:
        if not self._subscribed:
            return
        for mode, keys in [
            ("ltpc", list(self._subscriptions._by_mode["ltpc"])),
            ("option_greeks", list(self._subscriptions._by_mode["option_greeks"])),
            ("full", list(self._subscriptions._by_mode["full"])),
            ("full_d30", list(self._subscriptions._by_mode["full_d30"])),
        ]:
            if keys:
                self._send_subscribe(keys, mode)

    def _send_subscribe(
        self, instrument_keys: list[str], mode: str, *, guid: str | None = None
    ) -> None:
        payload = build_subscribe_payload(instrument_keys, mode, guid=guid)
        self._send_raw("sub", payload)

    def _send_raw(self, method: str, payload: dict[str, Any]) -> None:
        if self._socket is None:
            return
        send = getattr(self._socket, "send", None)
        if send is None:
            return
        try:
            send(encode_subscribe_payload(payload))
        except Exception as exc:
            logger.warning("Upstox V3 send failed: %s", exc)
            self._reconnect.record_failure()

    async def _read_loop(self) -> None:
        recv = getattr(self._socket, "recv", None)
        if recv is None:
            return
        while not self._stopped:
            try:
                raw = await recv() if asyncio.iscoroutinefunction(recv) else recv()
            except Exception as exc:
                logger.warning("Upstox V3 recv error: %s", exc)
                if not self._reconnect.should_retry():
                    break
                delay = self._reconnect.next_delay()
                self._reconnect.record_failure()
                await asyncio.sleep(delay)
                continue
            self._reconnect.reset()
            if not raw:
                continue
            if isinstance(raw, str):
                # First-tick is JSON with market_info
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "market_info":
                    for listener in self._listeners:
                        with contextlib.suppress(Exception):
                            listener("market_info", msg)
                continue
            try:
                frame = self._decoder.parse(raw)
            except Exception:
                continue
            if frame is None:
                continue
            for listener in self._listeners:
                with contextlib.suppress(Exception):
                    listener("tick", {"frame_type": frame.type, "payload": frame.payload})


def _default_socket_factory(url: str) -> Any:
    """Open a real ``websockets`` connection. Returns an awaitable that
    resolves to the connected WebSocket client."""
    try:
        import websockets  # type: ignore

        return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**20)
    except ImportError as exc:
        raise RuntimeError(
            "websockets library is required for live Upstox V3 WebSocket; "
            "install via `pip install websockets`"
        ) from exc
