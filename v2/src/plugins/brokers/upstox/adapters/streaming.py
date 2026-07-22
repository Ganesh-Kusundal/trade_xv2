"""Upstox streaming adapter — quote + order callbacks."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from domain.entities import Order, Quote
from domain.value_objects import InstrumentId
from plugins.brokers.upstox.wire import UpstoxWire

OnQuote = Callable[[Quote], None]
OnOrder = Callable[[Order], None]
WsFactory = Callable[[str], Any]


class UpstoxStreamingAdapter:
    def __init__(
        self,
        *,
        wire: UpstoxWire,
        ws_url: str = "wss://api.upstox.com/v2/feed/market-data-feed",
        token_provider: Callable[[], str] | None = None,
        ws_factory: WsFactory | None = None,
    ) -> None:
        self._wire = wire
        self._ws_url = ws_url
        self._token_provider = token_provider or (lambda: "")
        self._ws_factory = ws_factory
        self._quote_subs: dict[str, OnQuote | None] = {}
        self._order_cb: OnOrder | None = None
        self._ws: Any | None = None

    def stream(self, instrument_id: InstrumentId, on_quote: OnQuote | None = None) -> None:
        self._quote_subs[instrument_id.value] = on_quote
        self._ensure_ws()
        if self._ws is not None and hasattr(self._ws, "send"):
            key = self._wire.instrument_key(instrument_id)
            self._ws.send(json.dumps({"guid": "tx", "method": "sub", "data": {"mode": "full", "instrumentKeys": [key]}}))

    def unstream(self, instrument_id: InstrumentId) -> None:
        self._quote_subs.pop(instrument_id.value, None)

    def stream_order(self, on_order: OnOrder | None = None) -> None:
        self._order_cb = on_order
        self._ensure_ws()

    def feed_raw(self, payload: dict[str, Any]) -> None:
        if "order_id" in payload or payload.get("type") == "order":
            if self._order_cb is not None:
                self._order_cb(self._wire.to_order(payload))
            return
        iid_raw = payload.get("instrument_id") or payload.get("symbol")
        if iid_raw and iid_raw in self._quote_subs:
            cb = self._quote_subs[iid_raw]
            if cb is not None:
                cb(self._wire.to_quote(payload, instrument_id=InstrumentId(value=str(iid_raw))))

    def close(self) -> None:
        if self._ws is not None and hasattr(self._ws, "close"):
            self._ws.close()
        self._ws = None

    def _ensure_ws(self) -> None:
        if self._ws is not None or self._ws_factory is None:
            return
        # Upstox authorizes feed via REST then connects; factory gets URL+token
        self._ws = self._ws_factory(f"{self._ws_url}?token={self._token_provider()}")
