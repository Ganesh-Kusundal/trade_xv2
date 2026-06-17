"""BrokerGateway — thin sync facade delegating to DhanConnection ports."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from brokers.common.core.domain import Balance, MarketDepth, OrderResponse, Quote
from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import (
    Holding,
    Order,
    Position,
    Trade,
)
from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT
from brokers.dhan.websocket import DhanMarketFeed

logger = logging.getLogger(__name__)


class BrokerGateway(MarketDataGateway):
    """Unified broker API. All calls delegate to connection adapters."""

    def __init__(self, connection: DhanConnection):
        self._conn = connection

    @property
    def extended(self) -> Any:
        """Access Dhan-specific capabilities beyond MarketDataGateway ABC.

        Returns a :class:`~brokers.dhan.extended.DhanExtendedCapabilities`
        instance with broker-specific methods (super orders, forever orders,
        conditional triggers, ledger, user profile, IP management, EDIS,
        option/futures listing, order validation).
        """
        from brokers.dhan.extended import DhanExtendedCapabilities
        return DhanExtendedCapabilities(self._conn)

    # ── Order shortcuts ──

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
        """Place an order with explicit parameters matching MarketDataGateway ABC.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`brokers.common.correlation.with_correlation`)
        is used.  This enables automatic end-to-end tracing from CLI
        commands through to the broker API.

        Args:
            symbol: Trading symbol
            exchange: Exchange segment (NSE, BSE, NFO, etc.)
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price (ignored for MARKET orders)
            order_type: MARKET, LIMIT, STOP_LOSS, STOP_LOSS_MARKET
            product_type: INTRADAY, DELIVERY, MARGIN, etc.
            validity: DAY or IOC
            trigger_price: Trigger price for SL orders
            correlation_id: Optional correlation ID for tracing

        Returns:
            OrderResponse with success status and order ID
        """
        if correlation_id is None:
            try:
                from brokers.common.correlation import get_current_correlation_id
                correlation_id = get_current_correlation_id()
            except ImportError:
                pass
        return self._conn.orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price if price > Decimal("0") else None,
            order_type=order_type,
            trigger_price=trigger_price if trigger_price > Decimal("0") else None,
            product_type=product_type,
            validity=validity,
            correlation_id=correlation_id,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._conn.orders.cancel_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self._conn.orders.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        return self._conn.orders.get_trade_book()

    # ── Lifecycle ──

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        self._conn.load_instruments(source=source, use_cache=use_cache)

    def close(self) -> None:
        self._conn.close()

    # ── Market Data (ABC-aligned) ─────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._conn.market_data.get_ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return self._conn.market_data.get_quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return self._conn.market_data.get_depth(symbol, exchange)

    def depth_20(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> MarketDepth:
        """Subscribe to 20-level market depth for *symbol* via WebSocket.

        On the first call the feed is created, the instrument subscribed, and
        the connection started.  Subsequent calls for the same feed reuse the
        existing WebSocket and subscription.

        The method returns the most-recently cached
        :class:`~brokers.common.core.domain.MarketDepth` (up to 20 levels on
        each side).  If no packet has been received yet it falls back to the
        5-level REST snapshot so callers always get *something*.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"NIFTY"``)
            exchange: Exchange (``"NSE"`` | ``"NFO"`` | ``"IDX_I"``)
            on_depth: Optional callback ``Callable[[MarketDepth], None]``
                      fired on every incoming depth packet.

        Raises:
            ValueError: For non-NSE exchanges (Dhan limitation).
        """
        # Dhan depth-20 only available on NSE segments.
        if exchange not in ("NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I"):
            raise ValueError(
                f"Depth 20 only supported for NSE segments, got: {exchange}"
            )


        inst = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)
        sid_str = inst.security_id
        sid_int = int(sid_str)

        feed = self._conn.depth_20_feed
        if feed is None:
            feed = self._conn.create_depth_20_feed(
                access_token=self._conn.access_token,
                instrument=(segment, sid_str),
            )
        else:
            # Add this instrument if not already subscribed.
            already = any(s[1] == sid_str for s in feed.subscriptions)
            if not already:
                feed.subscribe([(segment, sid_str)])

        # Register the caller’s callback.
        if on_depth is not None:
            feed.on_depth(on_depth)

        # Start the WebSocket if it’s not running yet.
        if not feed.is_running:
            feed.start()

        # Return the cached depth, falling back to 5-level REST if empty.
        cached = feed.latest_depth(sid_int)
        if cached is not None:
            return cached
        return self._conn.market_data.get_depth(symbol, exchange)

    def depth_200(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> MarketDepth:
        """Subscribe to 200-level market depth for *symbol* via WebSocket.

        Dhan allows only **one** instrument per depth-200 connection. Calling
        this method with a different symbol after the feed is already running
        raises :class:`ValueError`.

        Args:
            symbol:   Canonical trading symbol.
            exchange: Exchange (``"NSE"`` | ``"NFO"`` | ``"IDX_I"``)
            on_depth: Optional callback ``Callable[[MarketDepth], None]``.

        Raises:
            ValueError: For non-NSE exchanges or if the feed is already
                        subscribed to a different instrument.
        """
        # Dhan depth-200 only available on NSE segments.
        if exchange not in ("NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I"):
            raise ValueError(
                f"Depth 200 only supported for NSE segments, got: {exchange}"
            )


        inst = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)
        sid_str = inst.security_id

        feed = self._conn.depth_200_feed
        if feed is None:
            feed = self._conn.create_depth_200_feed(
                access_token=self._conn.access_token,
                instrument=(segment, sid_str),
            )
        else:
            # Already has a subscription — validate it’s the same instrument.
            existing = feed.subscriptions[0][1] if feed.subscriptions else None
            if existing and existing != sid_str:
                raise ValueError(
                    f"Depth 200 feed already subscribed to security_id {existing}. "
                    f"Create a new gateway connection to stream a different instrument."
                )

        # Register the caller’s callback.
        if on_depth is not None:
            feed.on_depth(on_depth)

        # Start the WebSocket if it’s not running yet.
        if not feed.is_running:
            feed.start()

        # Return the cached depth, falling back to 5-level REST if empty.
        cached = feed.latest_depth()
        if cached is not None:
            return cached
        return self._conn.market_data.get_depth(symbol, exchange)

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
        if isinstance(symbol, str):
            return self._conn.historical.get_historical(
                symbol, exchange, from_str, to_str, tf
            )
        frames = []
        for sym in symbol:
            df = self._conn.historical.get_historical(
                sym, exchange, from_str, to_str, tf
            )
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        """Get option chain. Delegates MCX-specific expiry lookup to extended."""
        return self.extended.get_option_chain(underlying, exchange, expiry)

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> dict:
        nfo_map = {"NIFTY": "NFO", "BANKNIFTY": "NFO", "FINNIFTY": "NFO", "SENSEX": "BFO"}
        dhan_exchange = nfo_map.get(underlying.upper(), exchange)
        contracts = self._conn.futures.get_contracts(underlying, dhan_exchange)
        expiries = self._conn.futures.get_expiries(underlying, dhan_exchange)
        chain = []
        for c in contracts:
            chain.append({
                "expiry": c.get("expiry", ""),
                "symbol": c.get("symbol", ""),
                "lot_size": c.get("lot_size", 1),
                "underlying": c.get("underlying", underlying),
            })
        return {"underlying": underlying, "exchange": dhan_exchange, "expiries": expiries, "contracts": chain}

    def funds(self) -> Balance:
        return self._conn.portfolio.get_balance()

    def positions(self) -> list[Position]:
        return self._conn.portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        return self._conn.portfolio.get_holdings()

    def trades(self) -> list[Trade]:
        return self.get_trade_book()



    def describe(self) -> dict:
        instruments = self._conn.instruments
        return {
            "broker": "Dhan",
            "instruments_loaded": instruments._loaded,
            "instrument_count": instruments.stats().get("total", 0),
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    def capabilities(self) -> BrokerCapabilities:
        """Return Dhan broker capability matrix."""
        return BrokerCapabilities(
            expired_options=True,
            expired_futures=False,
            depth_20=True,
            depth_200=True,
            max_intraday_days=365 * 10,
            max_daily_days=365 * 10,
            supported_timeframes=("1m", "5m", "15m", "30m", "1h", "1D"),
            parallel_history=True,
            max_batch_size=1000,
            websocket=True,
            polling_fallback=True,
            order_types=("MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"),
            product_types=("INTRADAY", "MARGIN", "CNC", "MTF"),
            validities=("DAY", "IOC"),
            load_instruments=True,
            search=True,
            rate_limit_per_second=6,
            rate_limit_per_minute=200,
            # Advanced order types
            super_orders=True,
            forever_orders=True,
            conditional_triggers=True,
            slice_orders=True,
            # Account management
            ledger=True,
            user_profile=True,
            ip_management=True,
            edis=True,
            exit_all=True,
        )

    def search(self, query: str) -> list[dict]:
        results = []
        q = query.upper().strip()
        for inst in self._conn.instruments.all_instruments():
            if q in inst.symbol.upper() or q in (inst.canonical_symbol or "").upper():
                results.append({
                    "symbol": inst.symbol,
                    "exchange": inst.exchange.value,
                    "type": inst.instrument_type.value,
                    "security_id": inst.security_id,
                    "name": inst.canonical_symbol,
                })
                if len(results) >= 20:
                    break
        return results

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        The *on_tick* callback receives a canonical
        :class:`brokers.common.core.domain.Quote` object.  Broker-specific
        ``security_id`` values are never exposed to the caller.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"NIFTY"``).
            exchange: Exchange string (``"NSE"`` | ``"MCX"`` | ``"INDEX"`` …).
            mode:     Subscription mode — ``"LTP"`` | ``"QUOTE"`` | ``"DEPTH"``.
            on_tick:  Callable receiving a :class:`Quote`.
        """
        from brokers.common.core.domain import Quote
        inst = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)
        sid = int(inst.security_id)
        feed = self._conn.market_feed
        if feed is None:
            # Use token provider callable for fresh tokens
            feed = DhanMarketFeed(
                client_id=self._conn.client_id,
                access_token=self._conn.access_token,
                instruments=[(segment, sid, mode)],
                resolver=self._conn.instruments,
                access_token_fn=lambda: self._conn.access_token,
                event_bus=self._conn.event_bus,
            )
            self._conn.market_feed = feed
        else:
            feed.subscribe([(segment, sid, mode)])
        if on_tick:
            # Wrap the raw dict from _transform_quote into a canonical Quote.
            # The dict has keys: symbol, security_id, ltp, open, high, low,
            # close, volume, change.  security_id is never forwarded.
            def _wrap(data: dict) -> None:
                try:
                    q = Quote(
                        symbol=data.get("symbol", symbol),
                        ltp=data.get("ltp", Decimal("0")),
                        open=data.get("open", Decimal("0")),
                        high=data.get("high", Decimal("0")),
                        low=data.get("low", Decimal("0")),
                        close=data.get("close", Decimal("0")),
                        volume=int(data.get("volume", 0)),
                        change=data.get("change", Decimal("0")),
                    )
                    on_tick(q)
                except Exception:
                    import logging as _log
                    _log.getLogger(__name__).debug(
                        "Dhan tick→Quote wrap failed; forwarding raw",
                        exc_info=True,
                    )
                    on_tick(data)
            feed.on_quote(_wrap)
        if not feed.is_connected:
            feed.connect()
        return feed

    # ── Parallel Data Fetching ──────────────────────────────────────

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Fetch LTP for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_ltp(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Any]:
        """Fetch quotes for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_quote(symbols, exchange)

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Fetch history for multiple symbols in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        frames = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.history, sym, exchange, timeframe, lookback_days): sym
                for sym in symbols
            }
            for future in as_completed(futures):
                try:
                    df = future.result()
                    if not df.empty:
                        frames.append(df)
                except Exception as exc:
                    logger.debug("history_batch_future_failed: %s", exc)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

