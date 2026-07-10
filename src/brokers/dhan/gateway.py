"""BrokerGateway — thin sync facade delegating to DhanConnection ports."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from domain import Balance, MarketDepth, OrderResponse, Quote
from brokers.dhan.streaming.connection import DhanConnection
from brokers.dhan.domain import (
    Holding,
    Order,
    Position,
    Trade,
)
from brokers.common.capabilities_validator import enforce_gateway_capabilities
from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT
from brokers.common.broker_capabilities import BrokerCapabilities

logger = logging.getLogger(__name__)


class DhanBrokerGateway:
    """Unified broker API. All calls delegate to connection adapters.

    Strangler-fig shim: declarative wire policy is available via :attr:`wire`
    (``brokers.dhan.wire.DhanWireAdapter``). Callers should migrate to the
    wire adapter + kernel; this gateway remains during Stage 3/4.
    """

    def __init__(self, connection: DhanConnection):
        self._conn = connection
        from brokers.dhan.wire import build_dhan_wire

        self._wire = build_dhan_wire()
        enforce_gateway_capabilities(self)

    @property
    def wire(self):
        return self._wire

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
                from domain.correlation import get_current_correlation_id

                correlation_id = get_current_correlation_id()
            except ImportError:
                pass
        # OrdersAdapter expects BrokerOrderPayload (not flat kwargs).
        from domain.enums import OrderType, ProductType, Side, Validity
        from domain.market_enums import ExchangeSegment
        from domain.models.dtos import BrokerOrderPayload

        side_e = side if isinstance(side, Side) else Side(str(side).upper())
        if isinstance(order_type, OrderType):
            ot_e = order_type
        else:
            ot_raw = str(order_type).upper().replace("-", "_").replace(" ", "_")
            aliases = {
                "SL": "STOP_LOSS",
                "STOPLOSS": "STOP_LOSS",
                "SLM": "STOP_LOSS_MARKET",
                "STOPLOSS_MARKET": "STOP_LOSS_MARKET",
            }
            ot_e = OrderType(aliases.get(ot_raw, ot_raw))
        pt_e = (
            product_type
            if isinstance(product_type, ProductType)
            else ProductType(str(product_type).upper())
        )
        val_e = (
            validity if isinstance(validity, Validity) else Validity(str(validity).upper())
        )
        segment = EXCHANGE_TO_SEGMENT.get(str(exchange).upper(), DEFAULT_SEGMENT)
        try:
            exch_seg = (
                segment
                if isinstance(segment, ExchangeSegment)
                else ExchangeSegment(str(segment))
            )
        except Exception:
            exch_seg = ExchangeSegment.NSE

        payload = BrokerOrderPayload(
            symbol=symbol,
            exchange=exchange,
            transaction_type=side_e,
            quantity=int(quantity),
            price=price if price and price > Decimal("0") else None,
            trigger_price=(
                trigger_price if trigger_price and trigger_price > Decimal("0") else None
            ),
            order_type=ot_e,
            product_type=pt_e,
            validity=val_e,
            correlation_id=correlation_id,
            exchange_segment=exch_seg,
        )
        return self._conn.orders.place_order(payload)


    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._conn.orders.cancel_order(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an existing order, delegating to the orders adapter."""
        return self._conn.orders.modify_order(order_id, **changes)

    def cancel_all_orders(self, **kwargs: Any) -> list[tuple[str, bool]]:
        """Cancel all open orders, delegating to the orders adapter."""
        return self._conn.orders.cancel_all_orders()

    def get_order(self, order_id: str) -> Order:
        """Fetch a single order by id (parity with Upstox/Paper gateways)."""
        return self._conn.orders.get_order(order_id)

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

        Security mapping is internal to the connection — the gateway only
        passes canonical ``(symbol, exchange)``.
        """
        return self._conn.subscribe_depth_20(symbol, exchange, on_depth=on_depth)

    def depth_200(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> MarketDepth:
        """Subscribe to 200-level market depth for *symbol* via WebSocket.

        Security mapping is internal to the connection — the gateway only
        passes canonical ``(symbol, exchange)``.
        """
        return self._conn.subscribe_depth_200(symbol, exchange, on_depth=on_depth)

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
                "security_id": c.get("security_id", ""),
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
            "instruments_loaded": instruments.is_loaded(),
            "instrument_count": instruments.stats().get("total", 0),
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    def capabilities(self) -> BrokerCapabilities:
        """Return Dhan broker capability matrix (single source of truth)."""
        from brokers.dhan.config.capabilities import dhan_capabilities

        return dhan_capabilities()

    def list_capabilities(self):
        """CommonBrokerGateway-compatible capability descriptor (session kernel)."""
        from brokers.common.broker_capabilities import CapabilityDescriptor

        return CapabilityDescriptor.build(self.capabilities(), frozenset())

    def search(self, query: str) -> list[dict]:
        return self._conn.instruments.search(query)

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        The *on_tick* callback receives a canonical
        :class:`domain.Quote` object.  Broker-specific
        ``security_id`` values are never exposed to the caller — mapping is
        internal to the connection.
        """
        return self._conn.subscribe_stream(symbol, exchange, mode=mode, on_tick=on_tick)

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


# Back-compat alias
BrokerGateway = DhanBrokerGateway

