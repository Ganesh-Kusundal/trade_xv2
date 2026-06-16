"""BrokerGateway — thin sync facade delegating to DhanConnection ports."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

from brokers.common.gateway import MarketDataGateway, BrokerCapabilities
from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import Balance, Holding, MarketDepth, Order, Position, Quote, Trade


class BrokerGateway(MarketDataGateway):
    """Unified broker API. All calls delegate to connection adapters."""

    def __init__(self, connection: DhanConnection):
        self._conn = connection

    @property
    def instruments(self) -> Any:
        return self._conn.instruments

    @property
    def market_data(self) -> Any:
        return self._conn.market_data

    @property
    def orders(self) -> Any:
        return self._conn.orders

    @property
    def portfolio(self) -> Any:
        return self._conn.portfolio

    @property
    def options(self) -> Any:
        return self._conn.options

    @property
    def futures(self) -> Any:
        return self._conn.futures

    @property
    def historical(self) -> Any:
        return self._conn.historical

    @property
    def margin(self) -> Any:
        return self._conn.margin

    @property
    def alerts(self) -> Any:
        return self._conn.alerts

    # ── Order shortcuts ──

    def place_order(self, *args, **kwargs) -> Order:
        return self._conn.orders.place_order(*args, **kwargs)

    def cancel_order(self, order_id: str) -> bool:
        return self._conn.orders.cancel_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self._conn.orders.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        return self._conn.orders.get_trade_book()

    # ── Lifecycle ──

    def load_instruments(self, source: Optional[str] = None, use_cache: bool = True) -> None:
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
        on_depth: "Any | None" = None,
    ) -> MarketDepth:
        """Subscribe to 20-level market depth for *symbol* via WebSocket.

        On the first call the feed is created, the instrument subscribed, and
        the connection started.  Subsequent calls for the same feed reuse the
        existing WebSocket and subscription.

        The method returns the most-recently cached
        :class:`~brokers.common.core.models.MarketDepth` (up to 20 levels on
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

        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
        from brokers.dhan.depth_20 import DhanDepth20Feed

        inst    = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")
        sid_str = inst.security_id          # string for the subscription msg
        sid_int = int(sid_str)              # int for the cache key

        feed = self._conn._depth_20_feed
        if feed is None:
            feed = self._conn.create_depth_20_feed(
                access_token=self._conn._client.access_token,
                instrument=(segment, sid_str),
            )
        else:
            # Add this instrument if not already subscribed.
            already = any(s[1] == sid_str for s in feed._subscriptions)
            if not already:
                feed.subscribe([(segment, sid_str)])

        # Register the caller’s callback.
        if on_depth is not None:
            feed.on_depth(on_depth)

        # Start the WebSocket if it’s not running yet.
        if not (feed._thread and feed._thread.is_alive()):
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
        on_depth: "Any | None" = None,
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

        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
        from brokers.dhan.depth_200 import DhanDepth200Feed

        inst    = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")
        sid_str = inst.security_id

        feed = self._conn._depth_200_feed
        if feed is None:
            feed = self._conn.create_depth_200_feed(
                access_token=self._conn._client.access_token,
                instrument=(segment, sid_str),
            )
        else:
            # Already has a subscription — validate it’s the same instrument.
            existing = feed._subscriptions[0][1] if feed._subscriptions else None
            if existing and existing != sid_str:
                raise ValueError(
                    f"Depth 200 feed already subscribed to security_id {existing}. "
                    f"Create a new gateway connection to stream a different instrument."
                )

        # Register the caller’s callback.
        if on_depth is not None:
            feed.on_depth(on_depth)

        # Start the WebSocket if it’s not running yet.
        if not (feed._thread and feed._thread.is_alive()):
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
        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
        mcx_underlyings = {"CRUDEOIL", "CRUDEOILM", "GOLD", "SILVER", "COPPER", "ZINC", "NATURALGAS", "ALUMINIUM", "LEAD", "NIKKEI"}
        sec_id = None
        seg = None
        if underlying.upper() in mcx_underlyings and exchange.upper() == "MCX":
            seg = EXCHANGE_TO_SEGMENT.get("MCX", "MCX_COMM")
            futures = [
                i for i in self._conn.instruments.all_instruments()
                if i.symbol.upper().startswith(underlying.upper() + "-")
                and i.exchange.value == "MCX"
                and i.is_future
            ]
            futures.sort(key=lambda x: x.expiry or "")
            if futures:
                sec_id = int(futures[0].security_id)
        if expiry is None:
            if sec_id and seg:
                response = self._conn._client.post("/optionchain/expirylist", json={
                    "UnderlyingScrip": sec_id,
                    "UnderlyingSeg": seg,
                })
                raw = response.get("data", response)
                if isinstance(raw, dict):
                    expiries = raw.get("expiryList") or raw.get("expiries") or []
                elif isinstance(raw, list):
                    expiries = raw
                else:
                    expiries = []
            else:
                expiries = self.options.get_expiries(underlying, exchange)
            if not expiries:
                raise ValueError(f"No expiries found for {underlying}")
            expiry = expiries[0]
        if sec_id and seg:
            return self._conn.options.get_option_chain(underlying, exchange, expiry, security_id=sec_id)
        return self._conn.options.get_option_chain(underlying, exchange, expiry)

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> dict:
        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
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
        return {
            "broker": "Dhan",
            "instruments_loaded": self.instruments._loaded,
            "instrument_count": self.instruments.stats().get("total", 0),
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
        )

    def search(self, query: str) -> list[dict]:
        results = []
        q = query.upper().strip()
        for inst in self.instruments.all_instruments():
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
        :class:`brokers.common.core.models.Quote` object.  Broker-specific
        ``security_id`` values are never exposed to the caller.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"NIFTY"``).
            exchange: Exchange string (``"NSE"`` | ``"MCX"`` | ``"INDEX"`` …).
            mode:     Subscription mode — ``"LTP"`` | ``"QUOTE"`` | ``"DEPTH"``.
            on_tick:  Callable receiving a :class:`Quote`.
        """
        from brokers.common.core.models import Quote
        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT
        from brokers.dhan.websocket import DhanMarketFeed
        inst = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")
        sid = int(inst.security_id)
        feed = self._conn.market_feed
        if feed is None:
            # Use token provider callable for fresh tokens
            feed = DhanMarketFeed(
                client_id=self._conn._client.client_id,
                access_token=self._conn._client.access_token,
                instruments=[(segment, sid, mode)],
                resolver=self._conn.instruments,
                access_token_fn=lambda: self._conn._client.access_token,
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
                except Exception:
                    pass
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

