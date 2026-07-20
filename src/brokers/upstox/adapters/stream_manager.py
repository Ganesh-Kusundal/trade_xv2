"""Stream manager adapter — WebSocket subscription lifecycle management.

Responsibility: Manage WebSocket stream subscriptions with thread-safe
callback registration, deduplication, and cleanup.
Thread-safe: Uses threading.Lock for all subscription state mutations.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import TYPE_CHECKING, Any

from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter
from domain import Quote

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker

logger = logging.getLogger(__name__)


class StreamManagerAdapter:
    """Adapter for WebSocket stream subscription lifecycle management.

    Encapsulates:
    - Thread-safe callback registration and deduplication
    - WebSocket connection lifecycle (connect + subscribe)
    - Subscription cleanup and listener removal
    - Tick-to-Quote translation for incoming ticks

    Thread Safety:
        Uses _stream_lock to protect _stream_registry mutations.
        All subscription operations are atomic.

    Example::

        manager = StreamManagerAdapter(broker, instrument_resolver)
        ws = manager.subscribe("RELIANCE", "NSE", "LTP", on_tick=my_callback)
        manager.unsubscribe("RELIANCE", "NSE", on_tick=my_callback)
    """

    def __init__(
        self,
        broker: UpstoxBroker,
        instrument_resolver: Any,
    ) -> None:
        """Initialize with broker facade and instrument resolver.

        Args:
            broker: UpstoxBroker instance providing access to WebSocket client
            instrument_resolver: Resolver for translating instrument keys to definitions
        """
        self._broker = broker
        self._resolver = instrument_resolver
        self._stream_lock = threading.Lock()
        # Maps instrument_key → list of (on_tick_callback, wrapped_listener)
        self._stream_registry: dict[str, list[tuple[Any, Any]]] = {}

    def subscribe(
        self,
        symbol: str,
        exchange: str,
        mode: str,
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for symbol.

        Thread-safe: Uses _stream_lock to prevent race conditions during
        connect + subscribe. Callbacks are deduplicated via _stream_registry.

        Args:
            symbol: Canonical trading symbol (e.g., "RELIANCE")
            exchange: Exchange string (e.g., "NSE")
            mode: Subscription mode — "ltpc" | "full" | "option_greeks"
            on_tick: Callable receiving a Quote (or raw dict on resolution failure)

        Returns:
            WebSocket client instance
        """
        # Reuse the canonical resolution path (UpstoxInstrumentService.
        # resolve_instrument_key) instead of duplicating raw resolver.resolve()
        # + a synthesized fallback key here. The duplicated version had no
        # handling for bare MCX commodity symbols (e.g. "CRUDEOIL") -- it
        # fell back to a non-existent "MCX_FO|CRUDEOIL" key, so subscribing
        # silently produced zero ticks forever, with no error.
        inst_key = self._broker.instruments.resolve_instrument_key(symbol, exchange)
        ws = self._broker.market_data_websocket

        with self._stream_lock:
            # Dedup: check if this exact on_tick is already registered
            existing_pairs = self._stream_registry.get(inst_key, [])
            if on_tick is not None and any(cb is on_tick for cb, _ in existing_pairs):
                logger.debug(
                    "stream_callback_dedup",
                    extra={"symbol": symbol, "exchange": exchange},
                )
                return ws

            wrapped_listener = None
            if on_tick:

                def wrapped_listener(
                    _event_type: str,
                    raw: dict[str, Any],
                    _cb: Any = on_tick,
                    _key: str = inst_key,
                ) -> None:
                    # ws.add_listener() registers a connection-wide listener,
                    # not one scoped to this instrument -- every subscriber's
                    # wrapped_listener fires for every tick on the shared
                    # WebSocket. Without this filter, subscribing to two+
                    # symbols meant every callback received every other
                    # symbol's ticks too.
                    payload = (
                        raw.get("payload") if isinstance(raw, dict) and "payload" in raw else raw
                    )
                    tick_key = TickTranslatorAdapter._extract_instrument_key(payload)
                    if tick_key and tick_key != _key:
                        return
                    quote = self._translate_tick_to_quote(raw)
                    _cb(quote)

                ws.add_listener(wrapped_listener)
                self._stream_registry.setdefault(inst_key, []).append((on_tick, wrapped_listener))

            # is_connected can be True after an ephemeral-loop connect that
            # already closed — treat a dead task loop as needing reconnect.
            task = getattr(ws, "_task", None)
            loop_dead = (
                task is not None
                and hasattr(task, "get_loop")
                and task.get_loop().is_closed()
            )
            if not ws.is_connected or loop_dead:

                def _on_connected() -> None:
                    ws.subscribe([inst_key], mode.lower())

                # Long-lived WS read loop must not run on run_coro_sync's
                # ephemeral loop (it closes when connect() returns).
                from runtime.event_loop import ensure_runtime_loop_running
                from infrastructure.io.async_compat import connect_async_then

                ensure_runtime_loop_running()
                if loop_dead:
                    with contextlib.suppress(Exception):
                        # Clear stale connected flag before re-binding to runtime loop.
                        ws._connected = False
                        ws._task = None
                connect_async_then(ws.connect(), _on_connected)
            else:
                ws.subscribe([inst_key], mode.lower())

        return ws

    def unsubscribe(
        self,
        symbol: str,
        exchange: str,
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream.

        Removes the on_tick listener and SDK subscription. If on_tick
        is None, removes ALL listeners for the instrument.

        Args:
            symbol: Symbol to unsubscribe from
            exchange: Exchange string
            on_tick: The callback to remove. None removes all.
        """
        # Must match subscribe()'s resolution exactly, or unsubscribe looks
        # up the wrong registry key and silently no-ops.
        inst_key = self._broker.instruments.resolve_instrument_key(symbol, exchange)
        ws = self._broker.market_data_websocket

        with self._stream_lock:
            pairs = self._stream_registry.get(inst_key, [])
            if on_tick is not None:
                # Remove specific callback
                to_remove = [(cb, wl) for cb, wl in pairs if cb is on_tick]
                for cb, wl in to_remove:
                    pairs.remove((cb, wl))
                    if wl is not None:
                        ws.remove_listener(wl)
            else:
                # Remove ALL callbacks for this instrument
                for _cb, wl in pairs:
                    if wl is not None:
                        ws.remove_listener(wl)
                pairs.clear()

            if not pairs:
                self._stream_registry.pop(inst_key, None)
                # Unsubscribe from the SDK WebSocket
                try:
                    ws.unsubscribe([inst_key])
                except Exception as exc:
                    logger.debug("unstream_unsubscribe_failed: %s", exc)

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote | dict[str, Any]:
        """Translate raw tick to Quote using TickTranslatorAdapter.

        Args:
            raw: Raw tick payload from WebSocket

        Returns:
            Quote object or raw dict if translation fails
        """
        return TickTranslatorAdapter.translate(
            raw,
            resolve_callback=self._resolver.resolve,
        )

    @property
    def active_subscriptions(self) -> dict[str, int]:
        """Get count of active callbacks per instrument key.

        Returns:
            Dict mapping instrument_key to callback count
        """
        with self._stream_lock:
            return {key: len(pairs) for key, pairs in self._stream_registry.items()}
