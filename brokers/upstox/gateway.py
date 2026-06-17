"""UpstoxBrokerGateway — thin sync facade delegating to UpstoxBroker ports."""

from __future__ import annotations

import logging
import time
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from config.indices import index_upstox_key
from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.core.domain import (
    Balance,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
    DepthLevel,
)
from brokers.common.event_bus import EventBus
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.extended import UpstoxExtendedCapabilities
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

logger = logging.getLogger(__name__)


class UpstoxBrokerGateway(BatchFetchMixin, MarketDataGateway):
    """Unified Upstox broker API. All calls delegate to UpstoxBroker adapters."""

    def __init__(self, broker: UpstoxBroker):
        self._broker = broker

    # ── Market Data (ABC-aligned) ─────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        key = self._resolve_instrument_key(symbol, exchange)
        body = self._broker.market_data_v2.get_ltp([key])
        data = body.get("data", {})
        for _, v in data.items():
            if isinstance(v, dict) and "last_price" in v:
                return Decimal(str(v["last_price"]))
        return Decimal("0")

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        key = self._resolve_instrument_key(symbol, exchange)
        body = self._broker.market_data_v2.get_quote([key])
        data = body.get("data", {})
        for _, v in data.items():
            if isinstance(v, dict) and "last_price" in v:
                ltp = v.get("last_price", 0)
                ohlc = v.get("ohlc", {})
                return Quote(
                    symbol=symbol,
                    ltp=Decimal(str(ltp)),
                    open=Decimal(str(ohlc.get("open", 0))),
                    high=Decimal(str(ohlc.get("high", 0))),
                    low=Decimal(str(ohlc.get("low", 0))),
                    close=Decimal(str(ohlc.get("close", 0))),
                    volume=int(v.get("volume", 0)),
                    change=Decimal(str(v.get("net_change", 0))),
                )
        logger.warning("quote_not_found", extra={"symbol": symbol, "exchange": exchange})
        return Quote(symbol=symbol)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        key = self._resolve_instrument_key(symbol, exchange)
        body = self._broker.market_data_v2.get_order_book(key)
        data = body.get("data", {})
        depth = None
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, dict) and "depth" in v:
                    depth = v["depth"]
                    break
        buy = depth.get("buy", []) if isinstance(depth, dict) else []
        sell = depth.get("sell", []) if isinstance(depth, dict) else []
        bids = [DepthLevel(price=Decimal(str(level.get("price", 0))), quantity=int(level.get("quantity", 0)), orders=int(level.get("orders", 0))) for level in buy[:5]]
        asks = [DepthLevel(price=Decimal(str(level.get("price", 0))), quantity=int(level.get("quantity", 0)), orders=int(level.get("orders", 0))) for level in sell[:5]]
        return MarketDepth(bids=bids, asks=asks)

    def get_orderbook(self) -> list[Order]:
        return self._broker.order_query.get_order_list()

    def get_trade_book(self) -> list[Trade]:
        # Upstox has no dedicated trade-book endpoint. Return an empty list
        # (honoring the MarketDataGateway ABC contract) so callers such as
        # IntelligentGateway.trades() can fall back gracefully instead of
        # propagating NotImplementedError. Use get_orderbook() / order_query
        # to reconstruct trade-level detail.
        logger.debug(
            "upstox_trade_book_unavailable",
            extra={"hint": "Use gateway.get_orderbook() or broker.order_query.get_trades()"},
        )
        return []

    # ── Extended Capabilities ─────────────────────────────────────────

    @property
    def extended(self) -> Any:
        """Access Upstox-specific capabilities beyond MarketDataGateway ABC.

        Returns:
            UpstoxExtendedCapabilities instance with broker-specific methods

        Example::

            ipos = gateway.extended.get_ipos()
            pnl = gateway.extended.get_pnl("INE002A01018")
        """
        return UpstoxExtendedCapabilities(self._broker)

    # ── Lifecycle ──

    def load_instruments(self, source: str | None = None) -> None:
        cache_path = Path(".cache/upstox/complete.json.gz")
        if source:
            path = Path(source)
        elif cache_path.exists():
            path = cache_path
        else:
            path = self._broker.instrument_loader.download(cache_path)

        start = time.monotonic()
        defs = self._broker.instrument_loader.load(path)
        load_time = time.monotonic() - start
        logger.info(
            "instrument_load_completed",
            extra={"count": len(defs), "load_time_s": round(load_time, 2), "source": source or "cached"},
        )

        start = time.monotonic()
        self._broker.instrument_resolver.register_many(defs)
        memory_time = time.monotonic() - start
        logger.info(
            "instrument_memory_load_completed",
            extra={"count": len(defs), "memory_time_s": round(memory_time, 2)},
        )

    def close(self) -> None:
        self._broker.disconnect()

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        to_str = to_date or str(to_d)
        from_str = from_date or str(from_d)
        tf = timeframe.upper() if timeframe else "1D"

        # V3 interval mapping: (unit, interval)
        interval_map = {
            "1": ("minutes", "1"), "1MIN": ("minutes", "1"),
            "3": ("minutes", "3"), "3MIN": ("minutes", "3"),
            "5": ("minutes", "5"), "5MIN": ("minutes", "5"),
            "15": ("minutes", "15"), "15MIN": ("minutes", "15"),
            "30": ("minutes", "30"), "30MIN": ("minutes", "30"),
            "60": ("hours", "1"), "60MIN": ("hours", "1"),
            "1H": ("hours", "1"), "4H": ("hours", "4"),
            "1D": ("days", "1"), "D": ("days", "1"), "DAY": ("days", "1"),
            "1W": ("weeks", "1"), "W": ("weeks", "1"),
            "MON": ("months", "1"), "MONTH": ("months", "1"),
        }
        unit, interval = interval_map.get(tf, ("days", "1"))

        if isinstance(symbol, str):
            return self._fetch_history(symbol, exchange, from_str, to_str, unit, interval)
        frames = []
        for sym in symbol:
            df = self._fetch_history(sym, exchange, from_str, to_str, unit, interval)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _fetch_history(self, symbol: str, exchange: str, from_date: str, to_date: str, unit: str, interval: str) -> pd.DataFrame:
        key = self._resolve_instrument_key(symbol, exchange)
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()

        # V3 limits: 1 month for minutes, 1 quarter for hours, 1 decade for days
        if unit == "minutes":
            max_days = 30
        elif unit == "hours":
            max_days = 90
        else:
            max_days = 3650  # 10 years for days/weeks/months

        if (to_dt - from_dt).days > max_days:
            from_dt = to_dt - timedelta(days=max_days)

        # Use V3 client
        body = self._broker.historical_v3.get_candles(key, unit, interval, to_dt, from_dt)
        data = body.get("data", {})
        if isinstance(data, dict):
            candles = data.get("candles", [])
        elif isinstance(data, list):
            candles = data
        else:
            candles = []
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi", "symbol", "exchange", "timeframe"])
        records = []
        for c in candles:
            if isinstance(c, list) and len(c) >= 6:
                records.append({
                    "timestamp": pd.to_datetime(c[0]),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": int(c[5]),
                    "oi": int(c[6]) if len(c) > 6 else 0,
                    "symbol": symbol,
                    "exchange": exchange,
                    "timeframe": interval,
                })
        return pd.DataFrame(records)

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        raise NotImplementedError(
            "Upstox option chain endpoint is deprecated. Use Dhan for option chains."
        )

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> dict:
        raise NotImplementedError(
            "Upstox future chain is not supported. Use Dhan for future chains."
        )

    def funds(self) -> Balance:
        return self._broker.portfolio.get_fund_limits()

    def positions(self) -> list[Position]:
        return self._broker.portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        return self._broker.portfolio.get_holdings()



    def trades(self) -> list[Trade]:
        return self.get_trade_book()

    def describe(self) -> dict:
        return {
            "broker": "Upstox",
            "instruments_loaded": self._broker.instrument_resolver.is_loaded() if hasattr(self._broker.instrument_resolver, 'is_loaded') else True,
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    def capabilities(self) -> BrokerCapabilities:
        """Return Upstox broker capability matrix."""
        return BrokerCapabilities(
            expired_options=False,
            expired_futures=False,
            depth_20=False,
            depth_200=False,
            max_intraday_days=30,
            max_daily_days=365 * 10,
            supported_timeframes=("1m", "5m", "15m", "30m", "1h", "1D"),
            parallel_history=True,
            max_batch_size=10,
            websocket=True,
            polling_fallback=False,
            order_types=("MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"),
            product_types=("INTRADAY", "MARGIN", "CNC"),
            validities=("DAY", "IOC"),
            load_instruments=True,
            search=True,
            rate_limit_per_second=10,
            rate_limit_per_minute=200,
            # Investment capabilities
            ipo=True,
            mutual_funds=True,
            fundamentals=True,
            payments=True,
            # Account management
            user_profile=True,
            convert_position=True,
            trade_pnl=True,
        )

    def search(self, query: str) -> list[dict]:
        results = []
        q = query.upper().strip()
        if hasattr(self._broker.instrument_resolver, 'search'):
            results = self._broker.instrument_resolver.search(q)
        return results[:20] if isinstance(results, list) else []

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        The *on_tick* callback receives a canonical :class:`brokers.common.core.domain.Quote`
        object — broker-specific ``instrument_key`` values are never exposed to
        the caller.  If the resolver does not find a definition for the incoming
        key the raw payload dict is forwarded instead so nothing is silently
        dropped.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"RELIANCE"``)
            exchange: Exchange string (e.g. ``"NSE"``)
            mode:     Subscription mode — ``"ltpc"`` | ``"full"`` | ``"option_greeks"``
            on_tick:  Callable receiving a :class:`Quote` (or raw dict on
                      resolution failure)
        """
        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        key = f"{segment}|{symbol}"
        ws = self._broker.market_data_websocket

        # Wrap the caller's on_tick so it receives a Quote, not raw broker data.
        wrapped_listener = None
        if on_tick:
            def wrapped_listener(_event_type: str, raw: dict[str, Any]) -> None:
                quote = self._translate_tick_to_quote(raw)
                on_tick(quote)

        # WebSocket connect is async — schedule connect+subscribe atomically.
        # run_async_compat_with_subscribe guarantees ordering: subscribe
        # only runs after connect completes, even in async context.
        if not ws.is_connected:
            def _on_connected() -> None:
                ws.subscribe([key], mode.lower())
                if wrapped_listener:
                    ws.add_listener(wrapped_listener)
            from brokers.common.async_compat import connect_async_then
            connect_async_then(ws.connect(), _on_connected)
        else:
            # Already connected — subscribe and register listener directly.
            ws.subscribe([key], mode.lower())
            if wrapped_listener:
                ws.add_listener(wrapped_listener)
        return ws

    # ── Internal ──

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        """Return the Upstox instrument_key for a canonical symbol.

        For index symbols (NIFTY, BANKNIFTY, etc.) the hardcoded mapping
        in :mod:`config.indices` is checked first, since indices use a
        different segment (``NSE_INDEX``) than equities (``NSE_EQ``).
        """

        # 1. Check hardcoded index mapping first (indices have different segment)
        idx_key = index_upstox_key(symbol)
        if idx_key is not None:
            # Verify the key resolves (the asset JSON includes indices)
            defn = self._broker.instrument_resolver.resolve(instrument_key=idx_key)
            if defn:
                return defn.instrument_key
            # Fall through — return the hardcoded key anyway (it's a known index)
            return idx_key

        # 2. Normal segment resolution for equities/F&O
        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        if segment == 'NSE':
            segment = 'NSE_EQ'
        elif segment == 'BSE':
            segment = 'BSE_EQ'
        defn = self._broker.instrument_resolver.resolve(symbol=symbol, exchange_segment=segment)
        if defn:
            return defn.instrument_key
        return f"{segment}|{symbol}"

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote | dict[str, Any]:
        """Translate a raw WebSocket tick frame into a canonical :class:`Quote`.

        The incoming *raw* dict has the shape produced by
        :class:`brokers.upstox.websocket.market_data_v3.UpstoxMarketDataV3Multiplexer`:

        .. code-block:: python

            {
                "frame_type": "ltpc" | "full" | "option_greeks" | ...,
                "payload": <protobuf-decoded object or dict>,
            }

        Resolution flow:

        1. Extract ``instrument_key`` from the payload.
        2. Reverse-resolve the key to a :class:`~brokers.upstox.instruments.definition.UpstoxInstrumentDefinition`.
        3. Derive a canonical symbol via :meth:`_canonical_symbol_for_defn`.
        4. Build and return a :class:`~brokers.common.core.domain.Quote`.

        If the key cannot be resolved the raw dict is returned unchanged so
        no data is silently dropped.
        """
        try:
            payload = raw.get("payload") if isinstance(raw, dict) else raw
            if payload is None:
                return raw

            # Extract instrument_key — Protobuf objects use attribute access;
            # dict payloads (e.g. backfill bars) use key access.
            if isinstance(payload, dict):
                inst_key = payload.get("instrument_key") or payload.get("instrumentKey", "")
            else:
                inst_key = (
                    getattr(payload, "instrument_key", None)
                    or getattr(payload, "instrumentKey", "")
                )

            if not inst_key:
                return raw

            # Resolve broker key → instrument definition
            defn = self._broker.instrument_resolver.resolve(instrument_key=inst_key)
            canonical_sym = self._canonical_symbol_for_defn(defn, inst_key)

            # Extract price fields — prefer attribute access (Protobuf), then dict
            def _f(name: str, default: float = 0.0) -> Decimal:
                if isinstance(payload, dict):
                    return Decimal(str(payload.get(name, default)))
                return Decimal(str(getattr(payload, name, default) or default))

            def _i(name: str) -> int:
                if isinstance(payload, dict):
                    return int(payload.get(name, 0) or 0)
                return int(getattr(payload, name, 0) or 0)

            # LTPC fields: last_price, close (prev close)
            ltp   = _f("last_price") or _f("ltp")
            close = _f("close_price") or _f("close") or _f("prev_close_price")

            # OHLC — present in full / option_greeks modes
            ohlc  = payload.get("ohlc", {}) if isinstance(payload, dict) else getattr(payload, "ohlc", None)
            if isinstance(ohlc, dict):
                open_ = Decimal(str(ohlc.get("open", 0) or 0))
                high  = Decimal(str(ohlc.get("high", 0) or 0))
                low   = Decimal(str(ohlc.get("low",  0) or 0))
                cl    = Decimal(str(ohlc.get("close", 0) or 0))
                if cl:
                    close = cl
            elif ohlc is not None:
                open_ = Decimal(str(getattr(ohlc, "open", 0) or 0))
                high  = Decimal(str(getattr(ohlc, "high", 0) or 0))
                low   = Decimal(str(getattr(ohlc, "low",  0) or 0))
                cl    = Decimal(str(getattr(ohlc, "close", 0) or 0))
                if cl:
                    close = cl
            else:
                open_ = _f("open")
                high  = _f("high")
                low   = _f("low")

            volume = _i("volume") or _i("total_buy_quantity") + _i("total_sell_quantity")

            # Best bid/ask
            bid = _f("best_bid_price") or None
            ask = _f("best_ask_price") or None
            if bid is not None and bid == Decimal("0"):
                bid = None
            if ask is not None and ask == Decimal("0"):
                ask = None

            # Timestamp
            ts = None
            try:
                ts_raw = (
                    payload.get("exchange_timestamp") if isinstance(payload, dict)
                    else getattr(payload, "exchange_timestamp", None)
                )
                if ts_raw:
                    if isinstance(ts_raw, int | float):
                        ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)
                    elif isinstance(ts_raw, str):
                        ts = datetime.fromisoformat(ts_raw)
                    else:
                        ts = ts_raw
            except Exception:
                ts = None

            return Quote(
                symbol=canonical_sym,
                ltp=ltp,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                change=ltp - close if ltp and close else Decimal("0"),
                bid=bid,
                ask=ask,
                timestamp=ts,
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "Upstox tick translation failed; forwarding raw payload",
                exc_info=True,
            )
            return raw

    @staticmethod
    def _canonical_symbol_for_defn(
        defn: Any,  # UpstoxInstrumentDefinition | None
        fallback_key: str = "",
    ) -> str:
        """Derive a clean, user-facing canonical symbol from a definition.

        Priority:

        1. ``defn.name`` — the long-form canonical name (e.g. ``"NIFTY 29 MAY 25 24800 CE"``).
        2. ``defn.symbol`` — trading symbol.
        3. ``defn.trading_symbol``
        4. RHS of the ``instrument_key`` fallback (e.g. ``"NSE_EQ|RELIANCE"`` → ``"RELIANCE"``).
        """
        if defn is None:
            if fallback_key and "|" in fallback_key:
                return fallback_key.split("|", 1)[1]
            return fallback_key
        if defn.name:
            return defn.name
        if defn.symbol:
            return defn.symbol
        if defn.trading_symbol:
            return defn.trading_symbol
        if fallback_key and "|" in fallback_key:
            return fallback_key.split("|", 1)[1]
        return fallback_key

    # ── MarketDataGateway required methods ──

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        """Place an order via Upstox.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`brokers.common.correlation.with_correlation`)
        is used for tracing.
        """
        if correlation_id is None:
            try:
                from brokers.common.correlation import get_current_correlation_id
                correlation_id = get_current_correlation_id()
            except ImportError:
                pass

        # Security guard: prevent live orders if disabled
        if not self._broker.settings.allow_live_orders:
            return OrderResponse(
                success=False,
                order_id="",
                message="Live orders are disabled. Set allow_live_orders=True in configuration.",
            )
        try:
            UpstoxDomainMapper.segment_to_wire(exchange)
            key = self._resolve_instrument_key(symbol, exchange)

            # Map order type
            ot_map = {"MARKET": "MKT", "LIMIT": "L", "STOP_LOSS": "SL", "STOP_LOSS_MARKET": "SL-M"}
            ot = ot_map.get(order_type, "MKT")

            # Map product type
            pt_map = {"INTRADAY": "I", "MARGIN": "I", "CNC": "C"}
            pt = pt_map.get(product_type, "I")

            # Map side
            side_val = 1 if side.upper() == "BUY" else 2

            body = self._broker.order_command.place_order(
                instrument_key=key,
                quantity=quantity,
                side=side_val,
                order_type=ot,
                product=pt,
                price=float(price),
                trigger_price=float(trigger_price),
                validity=validity,
            )

            data = body.get("data", {}) if isinstance(body, dict) else {}
            order_id = data.get("order_id", "") if isinstance(data, dict) else ""

            if correlation_id:
                logger.info("order_placed", extra={
                    "correlation_id": correlation_id,
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                })

            return OrderResponse(
                success=True,
                order_id=str(order_id),
                message="Order placed",
            )
        except Exception as e:
            logger.warning("order_placement_failed", extra={
                "correlation_id": correlation_id,
                "symbol": symbol,
                "side": side,
                "error": str(e),
            })
            return OrderResponse(
                success=False,
                order_id="",
                message=str(e),
            )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via Upstox.

        Returns:
            :class:`OrderResponse` with ``success`` reflecting the
            broker's response. Network/auth errors are reported as
            ``success=False`` with a diagnostic error code; this method
            never raises.
        """
        if not self._broker.settings.allow_live_orders:
            return OrderResponse.fail(
                message=(
                    "Live order cancellation is disabled. "
                    "Set allow_live_orders=True in configuration."
                ),
                error_code="BRO_ERR_NOT_SUPPORTED",
            )
        try:
            body = self._broker.order_client.cancel_order(order_id)
        except Exception as exc:
            logger.warning(
                "upstox_cancel_network_error",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return OrderResponse.fail(
                message=f"network error: {exc}",
                error_code="BRO_ERR_CONNECTION_FAILED",
            )
        if not isinstance(body, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(body)},
            )
        broker_status = str(body.get("status", "")).lower()
        if broker_status in {"success", "ok"}:
            return OrderResponse.ok(
                order_id=order_id,
                message=str(body.get("message", "Order cancelled")),
                raw_payload=body,
            )
        return OrderResponse.fail(
            message=str(
                body.get("errors", [{}])[0].get("message")
                if isinstance(body.get("errors"), list) and body.get("errors")
                else body.get("message", "Cancel failed")
            ),
            error_code=str(
                body.get("errors", [{}])[0].get("errorCode")
                if isinstance(body.get("errors"), list) and body.get("errors")
                else ""
            ),
            raw_payload=body,
        )
