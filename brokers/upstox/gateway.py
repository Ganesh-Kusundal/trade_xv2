"""UpstoxBrokerGateway — thin sync facade delegating to UpstoxBroker ports."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from brokers.common.core.domain import OrderResponse
from brokers.upstox.broker import UpstoxBroker


class UpstoxBrokerGateway(BatchFetchMixin, MarketDataGateway):
    """Unified Upstox broker API. All calls delegate to UpstoxBroker adapters."""

    def __init__(self, broker: UpstoxBroker):
        self._broker = broker

    @property
    def instruments(self) -> Any:
        return self._broker.instrument_resolver

    @property
    def market_data(self) -> Any:
        return self._broker.market_data

    @property
    def orders(self) -> Any:
        return self._broker.order_command

    @property
    def portfolio(self) -> Any:
        return self._broker.portfolio

    @property
    def options(self) -> Any:
        return self._broker.options

    @property
    def futures(self) -> Any:
        return self._broker.futures

    @property
    def historical(self) -> Any:
        return self

    @property
    def margin(self) -> Any:
        return self._broker.margin

    @property
    def news(self) -> Any:
        return self._broker.news

    @property
    def websocket(self) -> Any:
        return self._broker.market_data_websocket

    # ── Market Data (ABC-aligned) ─────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        key = self._resolve_instrument_key(symbol, exchange)
        body = self._broker.market_data_v2.get_ltp([key])
        data = body.get("data", {})
        for k, v in data.items():
            if isinstance(v, dict) and "last_price" in v:
                return Decimal(str(v["last_price"]))
        return Decimal("0")

    def quote(self, symbol: str, exchange: str = "NSE") -> Any:
        from brokers.common.core.domain import Quote
        key = self._resolve_instrument_key(symbol, exchange)
        body = self._broker.market_data_v2.get_quote([key])
        data = body.get("data", {})
        for k, v in data.items():
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
        return Quote(symbol=symbol)

    def depth(self, symbol: str, exchange: str = "NSE") -> Any:
        from brokers.common.core.domain import MarketDepth, DepthLevel
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
        bids = [DepthLevel(price=Decimal(str(l.get("price", 0))), quantity=int(l.get("quantity", 0)), orders=int(l.get("orders", 0))) for l in buy[:5]]
        asks = [DepthLevel(price=Decimal(str(l.get("price", 0))), quantity=int(l.get("quantity", 0)), orders=int(l.get("orders", 0))) for l in sell[:5]]
        return MarketDepth(bids=bids, asks=asks)

    def get_orderbook(self) -> list[Any]:
        return self._broker.order_query.get_order_list()

    def get_trade_book(self) -> list[Any]:
        return []

    # ── Lifecycle ──

    def load_instruments(self, source: Optional[str] = None) -> None:
        from pathlib import Path
        cache_path = Path(".cache/upstox/complete.json.gz")
        if source:
            path = Path(source)
        elif cache_path.exists():
            path = cache_path
        else:
            path = self._broker.instrument_loader.download(cache_path)
        defs = self._broker.instrument_loader.load(path)
        self._broker.instrument_resolver.register_many(defs)

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
        from datetime import datetime
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
        # Upstox option expiry endpoint is deprecated
        # Return empty chain with error message
        return {
            "underlying": underlying,
            "expiry": expiry or "N/A",
            "spot": 0,
            "strikes": [],
            "error": "Upstox option chain endpoint deprecated. Use Dhan for option chains."
        }

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> dict:
        return {"underlying": underlying, "exchange": "NSE_FO", "expiries": [], "contracts": []}

    def funds(self) -> Any:
        return self._broker.portfolio.get_fund_limits()

    def positions(self) -> list[Any]:
        return self._broker.portfolio.get_positions()

    def holdings(self) -> list[Any]:
        return self._broker.portfolio.get_holdings()

    def trades(self) -> list[Any]:
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
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        key = f"{segment}|{symbol}"
        ws = self._broker.market_data_websocket
        # WebSocket connect is async - schedule it if not connected
        if not ws.is_connected:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, schedule connect and subscribe
                    async def _connect_and_subscribe():
                        await ws.connect()
                        ws.subscribe([key], mode.lower())
                        if on_tick:
                            ws.add_listener(lambda _event_type, payload: on_tick(payload))
                    asyncio.ensure_future(_connect_and_subscribe())
                    return ws
                else:
                    loop.run_until_complete(ws.connect())
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(ws.connect())
        ws.subscribe([key], mode.lower())
        if on_tick:
            ws.add_listener(lambda _event_type, payload: on_tick(payload))
        return ws

    # ── Internal ──

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        if segment == 'NSE':
            segment = 'NSE_EQ'
        elif segment == 'BSE':
            segment = 'BSE_EQ'
        defn = self._broker.instrument_resolver.resolve(symbol=symbol, exchange_segment=segment)
        if defn:
            return defn.instrument_key
        return f"{segment}|{symbol}"

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
        """Place an order via Upstox."""
        try:
            from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
            segment = UpstoxDomainMapper.segment_to_wire(exchange)
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

            return OrderResponse(
                success=True,
                order_id=str(order_id),
                message="Order placed",
                correlation_id=correlation_id,
            )
        except Exception as e:
            return OrderResponse(
                success=False,
                order_id="",
                message=str(e),
                correlation_id=correlation_id,
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via Upstox."""
        try:
            body = self._broker.order_client.cancel_order(order_id)
            return body.get("status") == "success" if isinstance(body, dict) else False
        except Exception:
            return False
