"""Dhan WebSocket adapter — real-time market data and order updates."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from dhanhq.marketfeed import MarketFeed as SDKMarketFeed
from dhanhq.orderupdate import OrderUpdate as SDKOrderUpdate

from brokers.common.core.domain import (
    DepthLevel,
    MarketDepth,
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)
from brokers.common.event_bus import DomainEvent, EventBus

logger = logging.getLogger(__name__)

# SDK exchange segment constants
_EXCHANGE_MAP: dict[str, int] = {
    "IDX_I": SDKMarketFeed.IDX,
    "IDX": SDKMarketFeed.IDX,
    "NSE_EQ": SDKMarketFeed.NSE,
    "NSE": SDKMarketFeed.NSE,
    "NSE_FNO": SDKMarketFeed.NSE_FNO,
    "NFO": SDKMarketFeed.NSE_FNO,
    "NSE_CURRENCY": SDKMarketFeed.NSE_CURR,
    "CDS": SDKMarketFeed.NSE_CURR,
    "BSE_EQ": SDKMarketFeed.BSE,
    "BSE": SDKMarketFeed.BSE,
    "MCX_COMM": SDKMarketFeed.MCX,
    "MCX": SDKMarketFeed.MCX,
    "BSE_FNO": SDKMarketFeed.BSE_FNO,
    "BFO": SDKMarketFeed.BSE_FNO,
    "BSE_CURRENCY": SDKMarketFeed.BSE_CURR,
}

# SDK subscription type constants
_MODE_MAP: dict[str, int] = {
    "LTP": SDKMarketFeed.Ticker,
    "TICKER": SDKMarketFeed.Ticker,
    "QUOTE": SDKMarketFeed.Quote,
    "FULL": SDKMarketFeed.Quote,  # v2 uses Quote for full data
    "DEPTH": SDKMarketFeed.Quote,
}


def _to_sdk_instruments(instruments: list[tuple]) -> list[tuple]:
    """Convert human-readable instruments to SDK format.

    Accepts:
        [(exchange_str, security_id_str, mode_str), ...]
        e.g. [("MCX_COMM", "466583", "LTP")]

    Returns:
        [(exchange_int, security_id_int, type_int), ...]
        e.g. [(5, 466583, 15)]
    """
    sdk_instruments = []
    for item in instruments:
        if len(item) != 3:
            logger.warning("Skipping malformed instrument: %s", item)
            continue
        exchange, security_id, mode = item

        # Already SDK-format integers — pass through
        if isinstance(exchange, int) and isinstance(mode, int):
            sid_int = int(security_id)
            sdk_instruments.append((exchange, sid_int, mode))
            continue

        # Convert strings to SDK integers
        if isinstance(exchange, int):
            exch_int = exchange
        else:
            exch_int = _EXCHANGE_MAP.get(str(exchange).upper())
        if exch_int is None:
            logger.warning("Unknown exchange: %s", exchange)
            continue
        sid_int = int(security_id)
        mode_int = _MODE_MAP.get(str(mode).upper(), SDKMarketFeed.Ticker) if isinstance(mode, str) else int(mode)
        sdk_instruments.append((exch_int, sid_int, mode_int))
    return sdk_instruments


class _DhanContext:
    """Shim to satisfy SDK's dhan_context interface.

    Supports both static token and token provider callable.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token or ""
        self._access_token_fn = access_token_fn

    def get_client_id(self) -> str:
        return self._client_id

    def get_access_token(self) -> str:
        if self._access_token_fn:
            try:
                return self._access_token_fn()
            except Exception:
                pass
        return self._access_token

    def get_dhan_http(self):
        return None

    def update_token(self, token: str) -> None:
        """Update the static token snapshot."""
        self._access_token = token


class DhanMarketFeed:
    """Wraps the SDK's MarketFeed for real-time market data.

    Supports reconnect backfill: on reconnection, if a ``backfill_callback``
    was provided, it is invoked to fetch missed bars between the last tick
    time and the reconnection time.  The returned bars are published as TICK
    events so downstream subscribers see no gap.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        resolver=None,
        access_token_fn: Callable[[], str] | None = None,
        event_bus: EventBus | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
    ):
        """
        Initialize market feed.

        Args:
            client_id: Dhan client ID
            access_token: Dhan access token (static snapshot)
            access_token_fn: Callable returning fresh token (preferred over static)
            instruments: List of (exchange, security_id, mode) tuples.
                         Accepts strings ("MCX_COMM", "466583", "LTP") or
                         SDK integers (5, 466583, 15).
            resolver: Optional SymbolResolver for security_id → symbol lookup
            event_bus: Optional EventBus to publish TICK/DEPTH events to.
            backfill_callback: ``(symbol, from_dt, to_dt) -> list[dict]``
                Called on reconnect to fill the gap.  Each dict should have at
                minimum ``{"symbol": ..., "ltp": ..., "open": ..., "high": ...,
                "low": ..., "close": ..., "volume": ...}``.  Optional keys:
                ``"timestamp"`` (datetime).  If ``None``, no backfill occurs.
        """
        self._context = _DhanContext(
            client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
        )
        self._raw_instruments = instruments or []
        self._instruments = _to_sdk_instruments(instruments or [])
        self._resolver = resolver
        self._event_bus = event_bus
        self._backfill_callback = backfill_callback
        self._feed: Optional[SDKMarketFeed] = None
        self._thread: Optional[threading.Thread] = None
        self._is_connected = False
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._quote_callbacks: list[Callable[[dict], None]] = []
        self._depth_callbacks: list[Callable[[dict], None]] = []
        # Reconnect backfill state
        self._last_tick_time: dict[str, datetime] = {}
        self._disconnect_time: datetime | None = None

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        self._context.update_token(access_token)

    def connect(self) -> None:
        """Start the WebSocket connection in a background daemon thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Market feed already connected")
                return

            if not self._instruments:
                logger.error("No valid instruments to subscribe")
                return

            self._stop_event.clear()
            self._is_connected = True
            self._feed = SDKMarketFeed(
                dhan_context=self._context,
                instruments=self._instruments,
                on_connect=self._on_connect,
                on_message=self._on_message,
                on_close=self._on_close,
                on_error=self._on_error,
            )

            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        """Run the market feed event loop with reconnection backoff."""
        backoff = 1.0
        max_backoff = 30.0
        while not self._stop_event.is_set():
            try:
                if self._feed is None:
                    break
                self._feed.run()
            except Exception as exc:
                err_str = str(exc).lower()
                if "no close frame" in err_str:
                    # Dhan server drops connections without close frames — expected
                    logger.debug("WebSocket closed without close frame (expected)")
                elif "429" in err_str:
                    logger.warning("WebSocket rate limited, backing off %ss", backoff)
                else:
                    logger.error("Market feed error: %s", exc)
            # Check if we should stop
            if self._stop_event.is_set():
                break
            # Backoff before reconnect; Event.wait is interruptible.
            if self._stop_event.wait(timeout=backoff):
                break
            backoff = min(backoff * 2, max_backoff)

    def disconnect(self) -> None:
        """Stop the WebSocket connection."""
        self._stop_event.set()
        with self._lock:
            self._is_connected = False
            feed = self._feed
        if feed:
            try:
                feed.close_connection()
            except Exception as exc:
                logger.warning("Error closing market feed: %s", exc)

    def subscribe(self, instruments: list[tuple]) -> None:
        """Add instruments to the subscription."""
        with self._lock:
            if not self._feed:
                raise RuntimeError("Not connected — call connect() first")
            sdk_instruments = _to_sdk_instruments(instruments)
            self._feed.subscribe_symbols(sdk_instruments)

    def unsubscribe(self, instruments: list[tuple]) -> None:
        """Remove instruments from the subscription."""
        with self._lock:
            if not self._feed:
                raise RuntimeError("Not connected — call connect() first")
            sdk_instruments = _to_sdk_instruments(instruments)
            self._feed.unsubscribe_symbols(sdk_instruments)

    def on_quote(self, callback: Callable[[dict], None]) -> None:
        """Register callback for quote updates."""
        with self._lock:
            self._quote_callbacks.append(callback)

    def on_depth(self, callback: Callable[[dict], None]) -> None:
        """Register callback for depth updates."""
        with self._lock:
            self._depth_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def _on_connect(self, feed) -> None:
        with self._lock:
            was_connected = self._is_connected
            self._is_connected = True
            disconnect_time = self._disconnect_time
            self._disconnect_time = None
        logger.info("Market feed connected")
        # On reconnect, backfill the gap if a callback was provided
        if not was_connected and disconnect_time is not None and self._backfill_callback is not None:
            self._backfill_gap(disconnect_time)

    def _backfill_gap(self, disconnect_time: datetime) -> None:
        """Fetch missed bars from REST and publish as TICK events."""
        now = datetime.now(timezone.utc)
        if disconnect_time >= now:
            return
        with self._lock:
            symbols = list(self._last_tick_time.keys())
        if not symbols:
            return
        logger.info(
            "Backfilling %d symbols for gap %s → %s",
            len(symbols),
            disconnect_time.isoformat(),
            now.isoformat(),
        )
        for symbol in symbols:
            try:
                bars = self._backfill_callback(symbol, disconnect_time, now)
                for bar in bars:
                    ts = bar.get("timestamp")
                    if ts is None:
                        bar["timestamp"] = now
                    self._publish_tick(bar)
                    # Update last tick time for backfilled bars
                    bar_ts = bar.get("timestamp", now)
                    if isinstance(bar_ts, datetime):
                        with self._lock:
                            prev = self._last_tick_time.get(symbol)
                            if prev is None or bar_ts > prev:
                                self._last_tick_time[symbol] = bar_ts
                if bars:
                    logger.debug("Backfilled %d bars for %s", len(bars), symbol)
            except Exception as exc:
                logger.warning("Backfill failed for %s: %s", symbol, exc)

    def _on_message(self, feed, data: dict) -> None:
        if not data:
            return
        data_type = data.get("type", "")
        if data_type in ("Ticker Data", "Quote Data"):
            quote = self._transform_quote(data)
            self._track_tick_time(quote)
            with self._lock:
                callbacks = list(self._quote_callbacks)
            for cb in callbacks:
                try:
                    cb(quote)
                except Exception as exc:
                    logger.error("Quote callback error: %s", exc)
            self._publish_tick(quote)
        elif data_type in ("Market Depth", "Full Data"):
            depth = self._transform_depth(data)
            with self._lock:
                callbacks = list(self._depth_callbacks)
            for cb in callbacks:
                try:
                    cb(depth)
                except Exception as exc:
                    logger.error("Depth callback error: %s", exc)
            self._publish_depth(depth)
        else:
            # Unknown type — still try to extract as quote
            quote = self._transform_quote(data)
            self._track_tick_time(quote)
            with self._lock:
                callbacks = list(self._quote_callbacks)
            for cb in callbacks:
                try:
                    cb(quote)
                except Exception:
                    pass
            self._publish_tick(quote)

    def _track_tick_time(self, quote: dict) -> None:
        """Record the latest tick time per symbol for gap detection."""
        symbol = quote.get("symbol")
        if not symbol:
            return
        now = datetime.now(timezone.utc)
        with self._lock:
            prev = self._last_tick_time.get(symbol)
            if prev is None or now > prev:
                self._last_tick_time[symbol] = now

    def _transform_quote(self, data: dict) -> dict:
        security_id = str(data.get("security_id", ""))
        symbol = security_id
        if self._resolver:
            try:
                inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception:
                pass
        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "open": Decimal(str(data.get("open", "0"))),
            "high": Decimal(str(data.get("high", "0"))),
            "low": Decimal(str(data.get("low", "0"))),
            "close": Decimal(str(data.get("close", "0"))),
            "volume": int(data.get("volume", 0)),
            "change": Decimal("0"),
        }

    def _transform_depth(self, data: dict) -> dict:
        security_id = str(data.get("security_id", ""))
        symbol = security_id
        if self._resolver:
            try:
                inst = self._resolver.get_by_security_id(security_id)
                if inst:
                    symbol = inst.symbol
            except Exception:
                pass
        return {
            "symbol": symbol,
            "security_id": security_id,
            "ltp": Decimal(str(data.get("last_price", data.get("LTP", "0")))),
            "depth": data.get("depth", []),
        }

    def _publish_tick(self, quote: dict) -> None:
        if self._event_bus is None:
            return
        try:
            q = Quote(
                symbol=quote.get("symbol", ""),
                ltp=quote.get("ltp", Decimal("0")),
                open=quote.get("open", Decimal("0")),
                high=quote.get("high", Decimal("0")),
                low=quote.get("low", Decimal("0")),
                close=quote.get("close", Decimal("0")),
                volume=quote.get("volume", 0),
                change=quote.get("change", Decimal("0")),
            )
            self._event_bus.publish(
                DomainEvent.now("TICK", {"quote": q}, symbol=q.symbol, source="DhanMarketFeed")
            )
        except Exception as exc:
            logger.error("EventBus TICK publish error: %s", exc)

    def _publish_depth(self, depth: dict) -> None:
        if self._event_bus is None:
            return
        try:
            d = depth.get("depth", {})
            bids = [
                DepthLevel(price=Decimal(str(b.get("price", 0))), quantity=int(b.get("quantity", 0)), orders=int(b.get("orders", 0)))
                for b in d.get("bids", [])
            ]
            asks = [
                DepthLevel(price=Decimal(str(a.get("price", 0))), quantity=int(a.get("quantity", 0)), orders=int(a.get("orders", 0)))
                for a in d.get("asks", [])
            ]
            md = MarketDepth(bids=bids, asks=asks)
            self._event_bus.publish(
                DomainEvent.now("DEPTH", {"depth": md}, symbol=depth.get("symbol", ""), source="DhanMarketFeed")
            )
        except Exception as exc:
            logger.error("EventBus DEPTH publish error: %s", exc)

    def _on_close(self, feed) -> None:
        with self._lock:
            self._is_connected = False
            self._disconnect_time = datetime.now(timezone.utc)
        logger.info("Market feed disconnected")

    def _on_error(self, feed, error) -> None:
        logger.error("Market feed error: %s", error)


class DhanOrderStream:
    """Wraps the SDK's OrderUpdate for real-time order status updates."""

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
        event_bus: EventBus | None = None,
    ):
        self._context = _DhanContext(
            client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
        )
        self._order_update: Optional[SDKOrderUpdate] = None
        self._thread: Optional[threading.Thread] = None
        self._is_connected = False
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._order_callbacks: list[Callable[[dict], None]] = []
        self._event_bus = event_bus

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        self._context.update_token(access_token)

    def connect(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Order stream already connected")
                return
            self._stop_event.clear()
            self._is_connected = True
            self._order_update = SDKOrderUpdate(dhan_context=self._context)
            self._order_update.on_update = self._on_order_update
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            with self._lock:
                ou = self._order_update
            if ou is None:
                return
            ou.connect_to_dhan_websocket_sync()
        except Exception as exc:
            logger.error("Order stream error: %s", exc)
        finally:
            with self._lock:
                self._is_connected = False

    def disconnect(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._is_connected = False

    def on_order_update(self, callback: Callable[[dict], None]) -> None:
        with self._lock:
            self._order_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def _on_order_update(self, data: dict) -> None:
        if not data or data.get("Type") != "order_alert":
            return
        order_data = data.get("Data", {})
        transformed = self._transform_order(order_data)
        with self._lock:
            callbacks = list(self._order_callbacks)
        for cb in callbacks:
            try:
                cb(transformed)
            except Exception as exc:
                logger.error("Order callback error: %s", exc)
        self._publish_order_update(transformed)

    @staticmethod
    def _transform_order(data: dict) -> dict:
        """Transform SDK order data to canonical format."""
        return {
            "order_id": str(data.get("orderNo", "")),
            "status": data.get("status", "UNKNOWN"),
            "symbol": data.get("tradingSymbol", ""),
            "exchange": data.get("exchangeSegment", "NSE"),
            "side": data.get("transactionType", "BUY"),
            "quantity": int(data.get("quantity", 0)),
            "filled_quantity": int(data.get("filledQty", 0)),
            "price": Decimal(str(data.get("price", "0"))),
            "average_price": Decimal(str(data.get("averagePrice", "0"))),
            "product_type": data.get("productType", "INTRADAY"),
            "order_type": data.get("orderType", "MARKET"),
            "validity": data.get("validity", "DAY"),
        }

    def _publish_order_update(self, data: dict) -> None:
        if self._event_bus is None:
            return
        try:
            status = OrderStatus.normalize(str(data.get("status", "OPEN")))
            side = Side.BUY if str(data.get("side", "")).upper() == "BUY" else Side.SELL
            order_type = OrderType(str(data.get("order_type", "MARKET")).upper())
            product_type = ProductType(str(data.get("product_type", "INTRADAY")).upper())
            validity = Validity(str(data.get("validity", "DAY")).upper())
            order = Order(
                order_id=str(data.get("order_id", "")),
                symbol=str(data.get("symbol", "")),
                exchange=str(data.get("exchange", "NSE")),
                side=side,
                order_type=order_type,
                quantity=int(data.get("quantity", 0)),
                filled_quantity=int(data.get("filled_quantity", 0)),
                price=data.get("price", Decimal("0")),
                avg_price=data.get("average_price", Decimal("0")),
                product_type=product_type,
                validity=validity,
                status=status,
                timestamp=datetime.now(timezone.utc),
            )
            self._event_bus.publish(
                DomainEvent.now("ORDER_UPDATED", {"order": order}, symbol=order.symbol, source="DhanOrderStream")
            )
            # If the update indicates a fill, also publish a TRADE event so the
            # PositionManager can update. Trade id is derived deterministically.
            filled = int(data.get("filled_quantity", 0))
            avg = data.get("average_price", Decimal("0"))
            if filled > 0 and avg > 0:
                trade = Trade(
                    trade_id=f"{order.order_id}:{filled}",
                    order_id=order.order_id,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    side=side,
                    quantity=filled,
                    price=avg,
                    timestamp=datetime.now(timezone.utc),
                    product_type=product_type,
                )
                self._event_bus.publish(
                    DomainEvent.now("TRADE", {"trade": trade}, symbol=trade.symbol, source="DhanOrderStream")
                )
        except Exception as exc:
            logger.error("EventBus ORDER_UPDATED publish error: %s", exc)


class PollingMarketFeed:
    """REST polling fallback for market data when WebSocket is unavailable.

    Polls /marketfeed/ltp at regular intervals and dispatches quote callbacks.
    Same callback interface as DhanMarketFeed for drop-in replacement.
    """

    def __init__(
        self,
        http_client,
        resolver,
        instruments: list[tuple],
        interval_seconds: float = 2.0,
    ):
        """
        Args:
            http_client: DhanHttpClient instance
            resolver: SymbolResolver for security_id → symbol lookup
            instruments: List of (exchange_str, security_id_str, mode_str) tuples
            interval_seconds: Polling interval (default 2s)
        """
        self._client = http_client
        self._resolver = resolver
        self._instruments = instruments
        self._interval = interval_seconds
        self._quote_callbacks: list[Callable[[dict], None]] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_connected = False

    def connect(self) -> None:
        """Start polling in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._is_connected = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Polling market feed started (interval=%ss)", self._interval)

    def disconnect(self) -> None:
        """Stop polling."""
        self._stop_event.set()
        self._is_connected = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Polling market feed stopped")

    def on_quote(self, callback: Callable[[dict], None]) -> None:
        """Register callback for quote updates."""
        self._quote_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def _poll_loop(self) -> None:
        """Poll each instrument and dispatch callbacks."""
        while not self._stop_event.is_set():
            for exchange, security_id, _mode in self._instruments:
                if self._stop_event.is_set():
                    break
                try:
                    from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
                    segment = EXCHANGE_TO_SEGMENT.get(str(exchange).upper(), "NSE_EQ")
                    sid = int(security_id)
                    data = self._client.post("/marketfeed/ltp", json={segment: [sid]})
                    raw = data.get("data", {}).get(segment, {}).get(str(sid), {})
                    ltp = raw.get("last_price", 0)

                    symbol = str(security_id)
                    if self._resolver:
                        inst = self._resolver.get_by_security_id(str(security_id))
                        if inst:
                            symbol = inst.symbol

                    quote = {
                        "symbol": symbol,
                        "security_id": str(security_id),
                        "ltp": Decimal(str(ltp)),
                        "open": Decimal("0"),
                        "high": Decimal("0"),
                        "low": Decimal("0"),
                        "close": Decimal("0"),
                        "volume": 0,
                        "change": Decimal("0"),
                    }
                    for cb in self._quote_callbacks:
                        try:
                            cb(quote)
                        except Exception as exc:
                            logger.error("Polling callback error: %s", exc)
                except Exception as exc:
                    logger.warning("Polling error for %s: %s", security_id, exc)

            self._stop_event.wait(timeout=self._interval)
