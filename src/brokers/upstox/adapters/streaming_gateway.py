"""StreamingGateway — WebSocket connections, tick parsing, stream handles.

Responsibility: Manage real-time streaming for market ticks, order updates,
and depth data via WebSocket connections.
Thread-safe: Uses stream_manager's internal locking for subscriptions.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

from brokers.upstox.adapters.stream_manager import StreamManagerAdapter
from domain import MarketDepth, Quote

logger = logging.getLogger(__name__)


class StreamingGateway:
    """Streaming operations — market ticks, order updates, depth streams.

    Encapsulates:
    - Market tick stream subscription/unsubscription
    - Order update stream via portfolio WebSocket
    - Depth (L2/L3) stream via market data WebSocket
    - Tick-to-domain-object translation
    - Connection status observability

    Thread Safety:
        Subscription state is managed by StreamManagerAdapter which uses
        threading.Lock for all mutations.

    Example::

        gw = StreamingGateway(broker, stream_manager, resolve_key_fn)
        handle = gw.stream("RELIANCE", "NSE", on_tick=my_cb)
        gw.unstream("RELIANCE", "NSE", on_tick=my_cb)
    """

    def __init__(
        self,
        broker: Any,
        stream_manager: StreamManagerAdapter,
        resolve_key_fn: Callable[[str, str], str],
    ) -> None:
        """Initialize with broker facade, stream manager, and key resolver.

        Args:
            broker: UpstoxBroker instance (for WebSocket access)
            stream_manager: StreamManagerAdapter for subscription lifecycle
            resolve_key_fn: Callable(symbol, exchange) -> instrument_key
        """
        self._broker = broker
        self._stream_manager = stream_manager
        self._resolve_key = resolve_key_fn

    # ── Market tick stream ──────────────────────────────────────────────

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        The *on_tick* callback receives a canonical :class:`domain.Quote`
        object — broker-specific ``instrument_key`` values are never exposed to
        the caller.  If the resolver does not find a definition for the incoming
        key the raw payload dict is forwarded instead so nothing is silently
        dropped.

        Thread-safe: uses ``_stream_lock`` to prevent race conditions during
        connect + subscribe. Callbacks are deduplicated via ``_stream_registry``
        so the same *on_tick* is not registered twice for the same instrument.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"RELIANCE"``)
            exchange: Exchange string (e.g. ``"NSE"``)
            mode:     Subscription mode — ``"ltpc"`` | ``"full"`` | ``"option_greeks"``
            on_tick:  Callable receiving a :class:`Quote` (or raw dict on
                      resolution failure)

        Returns:
            A handle scoped to this subscription — ``stop()``/``disconnect()``
            unsubscribe only this ``(symbol, exchange, on_tick)`` triple via
            :meth:`unstream`, leaving the shared WebSocket connection and any
            other active subscriptions untouched.
        """
        self._stream_manager.subscribe(symbol, exchange, mode, on_tick)

        stream_manager = self._stream_manager

        class LtpStreamHandle:
            def __init__(self, manager: Any, sym: str, exch: str, callback: Any) -> None:
                self._manager = manager
                self._symbol = sym
                self._exchange = exch
                self._on_tick = callback

            def stop(self, timeout: float | None = None) -> None:
                self._manager.unsubscribe(self._symbol, self._exchange, self._on_tick)

            def disconnect(self) -> None:
                self.stop()

        return LtpStreamHandle(stream_manager, symbol, exchange, on_tick)

    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream.

        Args:
            symbol: Symbol to unsubscribe
            exchange: Exchange string
            on_tick: The callback to remove. None removes all callbacks.
        """
        self._stream_manager.unsubscribe(symbol, exchange, on_tick)

    # ── Order update stream ─────────────────────────────────────────────

    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to order updates via Upstox portfolio stream.

        Returns:
            A connection service wrapper that can be stopped/started.
        """

        def portfolio_listener(event_type: str, payload: dict[str, Any]) -> None:
            if event_type == "order" and on_order is not None:
                from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

                on_order(UpstoxDomainMapper.to_order(payload))

        stream = self._broker.portfolio_stream

        from infrastructure.io.async_compat import connect_async_then
        from runtime.event_loop import ensure_runtime_loop_running

        if not stream.is_connected:

            def _on_connected() -> None:
                stream.add_listener(portfolio_listener)

            ensure_runtime_loop_running()
            connect_async_then(stream.connect(), _on_connected)
        else:
            stream.add_listener(portfolio_listener)

        class OrderStreamHandle:
            def __init__(self, stream_instance: Any, listener: Any) -> None:
                self._stream = stream_instance
                self._listener = listener

            def stop(self, timeout: Any = None) -> None:
                self._stream.remove_listener(self._listener)

            def disconnect(self) -> None:
                self._stream.remove_listener(self._listener)

        return OrderStreamHandle(stream, portfolio_listener)

    # ── Depth stream ────────────────────────────────────────────────────

    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        depth_type: str | None = None,  # DEPTH_5, DEPTH_30 — back-compat
        on_depth: Callable[[MarketDepth], None] | None = None,
        levels: int | None = None,
    ) -> Any:
        """Subscribe to Upstox L2 (D5) or L3 (D30) live WebSocket depth ticks.

        *levels* is the canonical entry point (mirrors Dhan's
        ``stream_depth(levels=...)``); *depth_type* is kept for existing
        callers. Passing neither defaults to 5-level depth.
        """
        from brokers.common.streaming import DepthStreamHandle

        if levels is not None:
            if levels not in (5, 30):
                raise ValueError(f"Upstox supports depth levels {{5, 30}}, got: {levels}")
            depth_type = "DEPTH_30" if levels == 30 else "DEPTH_5"
        elif depth_type is None:
            depth_type = "DEPTH_5"

        mode = "full_d30" if depth_type == "DEPTH_30" else "full"
        inst_key = self._resolve_key(symbol, exchange)

        def raw_depth_listener(event_type: str, raw_payload: dict[str, Any]) -> None:
            if event_type == "tick" and on_depth is not None:
                payload = raw_payload.get("payload", {})
                if payload:
                    depth_obj = self._translate_tick_to_depth(payload, symbol)
                    on_depth(depth_obj)

        ws = self._broker.market_data_websocket
        ws.add_listener(raw_depth_listener)

        from infrastructure.io.async_compat import connect_async_then
        from runtime.event_loop import ensure_runtime_loop_running

        if not ws.is_connected:

            def _on_connected() -> None:
                ws.subscribe([inst_key], mode)

            ensure_runtime_loop_running()
            connect_async_then(ws.connect(), _on_connected)
        else:
            ws.subscribe([inst_key], mode)

        def _stop() -> None:
            ws.remove_listener(raw_depth_listener)
            with contextlib.suppress(Exception):
                ws.unsubscribe([inst_key])

        return DepthStreamHandle(initial=None, on_stop=_stop)

    # ── Tick translation ────────────────────────────────────────────────

    def _translate_tick_to_depth(self, payload: dict[str, Any], symbol: str) -> MarketDepth:
        """Translate raw depth tick payload to MarketDepth domain model."""
        from datetime import datetime, timezone
        from decimal import Decimal

        from domain import DepthLevel

        raw_bids = payload.get("depth", {}).get("bids", [])
        raw_asks = payload.get("depth", {}).get("asks", [])

        bids = [
            DepthLevel(
                price=Decimal(str(b.get("price", 0))),
                quantity=int(b.get("quantity", 0)),
                orders=int(b.get("orders", 0)),
            )
            for b in raw_bids
        ]
        asks = [
            DepthLevel(
                price=Decimal(str(a.get("price", 0))),
                quantity=int(a.get("quantity", 0)),
                orders=int(a.get("orders", 0)),
            )
            for a in raw_asks
        ]

        depth_len = max(len(bids), len(asks))
        depth_type = "DEPTH_30" if depth_len > 20 else "DEPTH_5"

        return MarketDepth(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            depth_type=depth_type,
        )

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote | dict[str, Any]:
        """Translate raw tick to Quote (backward compatibility for tests).

        Delegates to TickTranslatorAdapter via StreamManagerAdapter.

        Args:
            raw: Raw tick payload

        Returns:
            Quote or raw dict
        """
        return self._stream_manager._translate_tick_to_quote(raw)

    # ── Connection status ───────────────────────────────────────────────

    def get_connection_status(self) -> dict[str, bool]:
        """Return connection status for all streams.

        Returns:
            Dict mapping WebSocket name to connected status
        """
        status: dict[str, bool] = {}
        for name in ("market_data_websocket", "portfolio_stream"):
            ws = getattr(self._broker, name, None)
            status[name] = bool(getattr(ws, "is_connected", False))
        return status

    # ── BrokerStreamGateway surface ─────────────────────────────────────

    def connect(self) -> bool:
        """Ensure market-data websocket is connected when available."""
        ws = getattr(self._broker, "market_data_websocket", None)
        if ws is None:
            return True
        if getattr(ws, "is_connected", False):
            return True
        connect_fn = getattr(ws, "connect", None)
        if callable(connect_fn):
            result = connect_fn()
            if result is False:
                return False
        return bool(getattr(ws, "is_connected", True))

    def subscribe(self, instruments: list[Any]) -> bool:
        """Subscribe instruments via the stream manager."""
        if not instruments:
            return True
        cb = getattr(self, "_stream_tick_callback", None)
        for item in instruments:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                symbol, exchange = str(item[0]), str(item[1])
            elif hasattr(item, "symbol"):
                symbol = str(item.symbol)
                exchange = str(getattr(item, "exchange", "NSE"))
            else:
                symbol, exchange = str(item), "NSE"
            self.stream(symbol, exchange, on_tick=cb)
        return True

    def on_tick(self, callback: Callable[[Any], None]) -> None:
        """Register default tick callback for subsequent subscribe() calls."""
        self._stream_tick_callback = callback

    def disconnect(self) -> None:
        """Disconnect market-data / order-stream websockets when present."""
        for name in ("market_data_websocket", "portfolio_stream"):
            ws = getattr(self._broker, name, None)
            if ws is None:
                continue
            stop = getattr(ws, "disconnect", None) or getattr(ws, "stop", None)
            if callable(stop):
                with contextlib.suppress(Exception):
                    stop()
