"""Dhan streaming — quote + order callbacks over injectable WS."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from domain.entities import Order, Quote
from domain.value_objects import InstrumentId
from plugins.brokers.dhan.wire import DhanWire

OnQuote = Callable[[Quote], None]
OnOrder = Callable[[Order], None]
WsFactory = Callable[[str], Any]


class DhanStreamingAdapter:
    """ponytail: callback multiplex; real WS factory injected (websockets or test double)."""

    def __init__(
        self,
        *,
        wire: DhanWire,
        ws_url: str = "wss://api-feed.dhan.co",
        token_provider: Callable[[], str] | None = None,
        client_id: str = "",
        ws_factory: WsFactory | None = None,
    ) -> None:
        self._wire = wire
        self._ws_url = ws_url
        self._token_provider = token_provider or (lambda: "")
        self._client_id = client_id
        self._ws_factory = ws_factory
        self._quote_subs: dict[str, OnQuote | None] = {}
        self._order_cb: OnOrder | None = None
        self._ws: Any | None = None

    def stream(self, instrument_id: InstrumentId, on_quote: OnQuote | None = None) -> None:
        self._quote_subs[instrument_id.value] = on_quote
        self._ensure_ws()
        if self._ws is not None and hasattr(self._ws, "send"):
            sec = self._wire.security_id(instrument_id)
            self._ws.send(
                json.dumps(
                    {
                        "RequestCode": 15,
                        "InstrumentCount": 1,
                        "InstrumentList": [{"ExchangeSegment": "NSE_EQ", "SecurityId": sec}],
                    }
                )
            )

    def unstream(self, instrument_id: InstrumentId) -> None:
        self._quote_subs.pop(instrument_id.value, None)

    def stream_order(self, on_order: OnOrder | None = None) -> None:
        self._order_cb = on_order
        self._ensure_ws()

    def feed_raw(self, payload: dict[str, Any]) -> None:
        """Test/ingress hook — decode venue payload into callbacks."""
        if "orderId" in payload or payload.get("type") == "order":
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
        url = f"{self._ws_url}?version=2&token={self._token_provider()}&clientId={self._client_id}"
        self._ws = self._ws_factory(url)
