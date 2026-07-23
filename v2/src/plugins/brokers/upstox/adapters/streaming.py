"""Upstox streaming adapter — quote + order callbacks."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from domain.entities import MarketDepth, Order, Quote
from domain.value_objects import InstrumentId
from plugins.brokers.common.ws_reconnect import ReconnectConfig, WsReconnectManager
from plugins.brokers.upstox.wire import UpstoxWire
from shared.errors import MappingError

logger = logging.getLogger(__name__)

OnQuote = Callable[[Quote], None]
OnOrder = Callable[[Order], None]
OnDepth = Callable[[MarketDepth], None]
WsFactory = Callable[[str], Any]


class UpstoxStreamingAdapter:
    def __init__(
        self,
        *,
        wire: UpstoxWire,
        ws_url: str = "wss://api.upstox.com/v2/feed/market-data-feed",
        token_provider: Callable[[], str] | None = None,
        ws_factory: WsFactory | None = None,
        reconnect_config: ReconnectConfig | None = None,
    ) -> None:
        self._wire = wire
        self._ws_url = ws_url
        self._token_provider = token_provider or (lambda: "")
        self._ws_factory = ws_factory
        self._quote_subs: dict[str, OnQuote | None] = {}
        self._order_cb: OnOrder | None = None
        self._depth_subs: dict[str, OnDepth | None] = {}
        self._last_depth: dict[str, MarketDepth] = {}
        self._ws: Any | None = None
        self._reconnect_manager = WsReconnectManager(reconnect_config)

    def stream_depth(
        self, instrument_id: InstrumentId, on_depth: OnDepth | None = None
    ) -> MarketDepth | None:
        """Subscribe to 20/200-level depth for *instrument_id*.

        Upstox's quote feed packet already carries ``depth.{buy,sell}``, so the
        same WS subscription serves both quote and depth. Returns the most
        recently cached depth (or ``None`` until the first packet arrives).
        """
        self._depth_subs[instrument_id.value] = on_depth
        self._ensure_ws()
        if self._ws is not None and hasattr(self._ws, "send"):
            key = self._wire.instrument_key(instrument_id)
            self._ws.send(json.dumps({"guid": "tx", "method": "sub", "data": {"mode": "full", "instrumentKeys": [key]}}))
        return self._last_depth.get(instrument_id.value)

    def stream(self, instrument_id: InstrumentId, on_quote: OnQuote | None = None) -> None:
        self._quote_subs[instrument_id.value] = on_quote
        self._ensure_ws()
        if self._ws is not None and hasattr(self._ws, "send"):
            key = self._wire.instrument_key(instrument_id)
            self._ws.send(json.dumps({"guid": "tx", "method": "sub", "data": {"mode": "full", "instrumentKeys": [key]}}))

    def unstream(self, instrument_id: InstrumentId) -> None:
        self._quote_subs.pop(instrument_id.value, None)

    def unstream_depth(self, instrument_id: InstrumentId) -> None:
        self._depth_subs.pop(instrument_id.value, None)
        self._last_depth.pop(instrument_id.value, None)

    def stream_order(self, on_order: OnOrder | None = None) -> None:
        self._order_cb = on_order
        self._ensure_ws()

    def feed_raw(self, payload: dict[str, Any]) -> None:
        if "order_id" in payload or payload.get("type") == "order":
            if self._order_cb is not None:
                try:
                    self._order_cb(self._wire.to_order(payload))
                except MappingError as exc:
                    logger.warning("upstox_order_update_unmapped: %s", exc)
            return
        iid_raw = payload.get("instrument_id") or payload.get("symbol")
        if iid_raw and iid_raw in self._quote_subs:
            cb = self._quote_subs[iid_raw]
            if cb is not None:
                cb(self._wire.to_quote(payload, instrument_id=InstrumentId.parse(str(iid_raw))))
        if iid_raw and iid_raw in self._depth_subs:
            depth_cb = self._depth_subs[iid_raw]
            depth = self._wire.to_depth(payload, instrument_id=InstrumentId.parse(str(iid_raw)))
            self._last_depth[iid_raw] = depth
            if depth_cb is not None:
                depth_cb(depth)

    def close(self) -> None:
        if self._ws is not None and hasattr(self._ws, "close"):
            self._ws.close()
        self._ws = None

    def _ensure_ws(self) -> None:
        if self._ws is not None or self._ws_factory is None:
            return
        # Upstox authorizes feed via REST then connects; factory gets URL+token
        self._ws = self._ws_factory(f"{self._ws_url}?token={self._token_provider()}")
        self._reconnect_manager.on_connect()

    def _handle_ws_close(self, close_code: int = 0, close_msg: str = "") -> None:
        self._reconnect_manager.on_close()
        self._ws = None
        thread = threading.Thread(target=self._do_reconnect, daemon=True)
        thread.start()

    def _do_reconnect(self) -> None:
        self._reconnect_manager.on_disconnect(
            reconnect_fn=self._ensure_ws,
            replay_fn=self._replay_subscriptions,
        )

    def _replay_subscriptions(self) -> None:
        for instrument_id_str in self._quote_subs:
            self._send_subscribe(InstrumentId.parse(instrument_id_str))
        for instrument_id_str in self._depth_subs:
            self._send_subscribe(InstrumentId.parse(instrument_id_str))
        if self._order_cb is not None:
            self._send_order_subscribe()

    def _send_subscribe(self, instrument_id: InstrumentId) -> None:
        if self._ws is not None and hasattr(self._ws, "send"):
            key = self._wire.instrument_key(instrument_id)
            self._ws.send(json.dumps({
                "guid": "tx",
                "method": "sub",
                "data": {"mode": "full", "instrumentKeys": [key]},
            }))

    def _send_order_subscribe(self) -> None:
        if self._ws is not None and hasattr(self._ws, "send"):
            self._ws.send(json.dumps({
                "guid": "tx",
                "method": "sub",
                "data": {"mode": "full", "instrumentKeys": []},
            }))
