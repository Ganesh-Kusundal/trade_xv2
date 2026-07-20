"""Dhan wire adapter — sanctioned transport boundary over DhanConnection."""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.broker_capabilities import BrokerCapabilities
from brokers.common.capabilities_validator import enforce_gateway_capabilities
from brokers.common.streaming import DepthStreamHandle
from brokers.common.wire_base import BaseWireAdapter
from brokers.dhan.domain import (
    Holding,
    Order,
    Position,
    Trade,
)
from brokers.dhan.config.capabilities import DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION
from brokers.dhan.streaming.connection import DhanConnection
from domain import Balance, MarketDepth, OrderResponse, Quote
from domain.constants import DEFAULT_DERIVATIVES_EXCHANGE, DEFAULT_EXCHANGE
from domain.entities.options import FutureChain

logger = logging.getLogger(__name__)


class DhanWireAdapter(BaseWireAdapter):
    """Unified Dhan broker API — all calls delegate to connection adapters."""

    # BrokerAdapter port requires a stable broker_id attribute.
    broker_id = "dhan"

    def __init__(self, connection: DhanConnection):
        self._conn = connection
        self._stream_lock = threading.Lock()
        enforce_gateway_capabilities(self)

    def _transport_connected(self) -> bool:
        """Authenticated + transport alive.

        A REST-only session (no WS feed yet) is connected when the HTTP client
        holds a usable access token. If a market feed exists, its socket state
        is authoritative.
        """
        conn = self._conn
        feed = getattr(conn, "market_feed", None) or getattr(conn, "_market_feed", None)
        if feed is not None and hasattr(feed, "is_connected"):
            return bool(feed.is_connected)
        client = getattr(conn, "_client", None)
        if client is not None:
            return bool((getattr(client, "access_token", None) or "").strip())
        return False

    def authenticate(self) -> bool:
        """Ensure Dhan session token is usable — parity with Upstox.connect().

        Prefers ``AuthManager.ensure_valid()`` when the factory wired auth onto
        the connection; otherwise ensures the HTTP client's access token via
        refresh. Does **not** report WebSocket feed liveness (that is
        ``is_connected``).
        """
        conn = self._conn
        auth = getattr(conn, "_auth", None)
        if auth is None:
            sm = getattr(conn, "_session_manager", None)
            auth = getattr(sm, "auth", None) if sm is not None else None
        if auth is not None:
            ensure = getattr(auth, "ensure_valid", None)
            if callable(ensure):
                try:
                    if ensure():
                        state = getattr(auth, "state", None)
                        token = getattr(state, "access_token", None) if state else None
                        client = getattr(conn, "_client", None)
                        if token and client is not None and hasattr(client, "update_token"):
                            client.update_token(token)
                        return True
                except Exception as exc:
                    logger.warning("dhan_authenticate_ensure_failed: %s", exc)
        client = getattr(conn, "_client", None)
        if client is None:
            return False
        if (getattr(client, "access_token", None) or "").strip():
            return True
        refresh = getattr(client, "_try_refresh_token", None)
        if callable(refresh):
            try:
                return bool(refresh())
            except Exception as exc:
                logger.warning("dhan_authenticate_refresh_failed: %s", exc)
                return False
        return False

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
        exchange: str = DEFAULT_EXCHANGE,
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
        from brokers.common.order_wire import order_request_to_payload
        from domain.enums import OrderType, ProductType, Side, Validity
        from domain.orders.requests import OrderRequest

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
        val_e = validity if isinstance(validity, Validity) else Validity(str(validity).upper())
        req = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            transaction_type=side_e,
            quantity=int(quantity),
            price=price if price and price > Decimal("0") else Decimal("0"),
            trigger_price=(
                trigger_price if trigger_price and trigger_price > Decimal("0") else None
            ),
            order_type=ot_e,
            product_type=pt_e,
            validity=val_e,
            correlation_id=correlation_id,
        )
        payload = order_request_to_payload(req, "dhan")
        return self._conn.orders.place_order(payload)

    def cancel_order(self, order_id: str) -> OrderResponse:
        result = self._conn.orders.cancel_order(order_id)
        if result.success:
            order = self.get_order(order_id)
            if order and order.status.name == "FILLED":
                from domain import OrderResponse as DomainOrderResponse
                from domain import OrderStatus

                return DomainOrderResponse(
                    success=False,
                    order_id=order_id,
                    message="Cancel failed: order already filled",
                    error_code="ALREADY_EXECUTED",
                    status=OrderStatus.REJECTED,
                )
        return result

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an existing order, delegating to the orders adapter."""
        return self._conn.orders.modify_order(order_id, **changes)

    def cancel_all_orders(self, **kwargs: Any) -> list[tuple[str, bool]]:
        """Cancel all open orders, delegating to the orders adapter."""
        return self._conn.orders.cancel_all_orders()

    def get_order(self, order_id: str) -> Order | None:
        """Fetch a single order by id (parity with Upstox/Paper gateways)."""
        try:
            return self._conn.orders.get_order(order_id)
        except Exception as e:
            logger.warning("get_order_failed", extra={"order_id": order_id, "error": str(e)})
            return None

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

    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        return self._conn.market_data.get_ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
        return self._conn.market_data.get_quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
        return self._conn.market_data.get_depth(symbol, exchange)

    def depth_20(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
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
        exchange: str = DEFAULT_EXCHANGE,
        on_depth: Any | None = None,
    ) -> MarketDepth:
        """Subscribe to 200-level market depth for *symbol* via WebSocket.

        Security mapping is internal to the connection — the gateway only
        passes canonical ``(symbol, exchange)``.
        """
        return self._conn.subscribe_depth_200(symbol, exchange, on_depth=on_depth)

    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        levels: int = 5,
        on_depth: Any | None = None,
    ) -> DepthStreamHandle:
        """Canonical depth-streaming entry point — dispatches by *levels*.

        Mirrors Upstox's ``stream_depth(levels=...)`` so callers can treat
        both gateways identically. Unlike ``depth_20``/``depth_200`` (kept
        for back-compat), the returned handle's ``.stop()`` unsubscribes only
        this symbol's WS subscription instead of requiring ``gateway.close()``.
        """
        from brokers.common.streaming import DepthStreamHandle

        if levels == 5:
            initial = self.depth(symbol, exchange)

            if on_depth is None:
                return DepthStreamHandle(initial=initial)

            # No separate depth-5 WS feed exists — Dhan's FULL-mode market
            # feed already carries an embedded 5-level ladder per tick
            # (see brokers.dhan.websocket._helpers._transform_depth), so
            # subscribe there instead of a one-shot REST snapshot. Matches
            # Upstox's levels=5, which is a genuinely live "full" mode stream.
            from decimal import Decimal as _Decimal

            from domain import DepthLevel

            def _on_raw_depth(data: dict) -> None:
                if data.get("symbol") != symbol:
                    return
                ladder = data.get("depth") or {}
                bids = [
                    DepthLevel(
                        price=_Decimal(str(b.get("price", 0))),
                        quantity=int(b.get("quantity", 0)),
                        orders=int(b.get("orders", 0)),
                    )
                    for b in ladder.get("bids", [])
                ]
                asks = [
                    DepthLevel(
                        price=_Decimal(str(a.get("price", 0))),
                        quantity=int(a.get("quantity", 0)),
                        orders=int(a.get("orders", 0)),
                    )
                    for a in ladder.get("asks", [])
                ]
                on_depth(MarketDepth(symbol=symbol, bids=bids, asks=asks, depth_type="DEPTH_5"))

            self.stream(symbol, exchange, mode="FULL", on_tick=None)
            feed = self._conn.market_feed
            if feed is not None:
                feed.on_depth(_on_raw_depth)

            def _stop() -> None:
                if feed is not None:
                    feed.off_depth(_on_raw_depth)
                self.unstream(symbol, exchange, on_tick=None)

            return DepthStreamHandle(initial=initial, on_stop=_stop)

        if levels == 20:
            initial = self.depth_20(symbol, exchange, on_depth=on_depth)

            def _stop() -> None:
                feed = self._conn.depth_20_feed
                if feed is not None:
                    ref = self._conn.instruments.resolve_dhan_ref(symbol, exchange)
                    feed.unsubscribe([(ref.exchange_segment, ref.security_id_str())])

            return DepthStreamHandle(initial=initial, on_stop=_stop)

        if levels == 200:
            initial = self.depth_200(symbol, exchange, on_depth=on_depth)

            def _stop() -> None:
                feed = self._conn.depth_200_feed
                if feed is not None:
                    ref = self._conn.instruments.resolve_dhan_ref(symbol, exchange)
                    feed.unsubscribe([(ref.exchange_segment, ref.security_id_str())])

            return DepthStreamHandle(initial=initial, on_stop=_stop)

        raise ValueError(f"Dhan supports depth levels {{5, 20, 200}}, got: {levels}")

    def history(
        self,
        symbol: str | list[str],
        exchange: str = DEFAULT_EXCHANGE,
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
            return self._conn.historical.get_historical(symbol, exchange, from_str, to_str, tf)
        frames = []
        for sym in symbol:
            df = self._conn.historical.get_historical(sym, exchange, from_str, to_str, tf)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> dict:
        """Get option chain. Delegates MCX-specific expiry lookup to data sub-facade."""
        from brokers.dhan.extended_data import DhanDataCapabilities

        return DhanDataCapabilities(self._conn).get_option_chain(underlying, exchange, expiry)

    def future_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
    ) -> FutureChain:
        from domain.entities.options import FutureChain, FutureContract

        nfo_map = {"NIFTY": "NFO", "BANKNIFTY": "NFO", "FINNIFTY": "NFO", "SENSEX": "BFO"}
        dhan_exchange = nfo_map.get(underlying.upper(), exchange)
        raw_contracts = self._conn.futures.get_contracts(underlying, dhan_exchange)
        expiries = self._conn.futures.get_expiries(underlying, dhan_exchange)
        contracts = tuple(
            FutureContract(
                symbol=str(c.get("symbol", "")),
                expiry=str(c.get("expiry", "")),
                lot_size=int(c.get("lot_size", 1) or 1),
                underlying=str(c.get("underlying", underlying)),
            )
            for c in raw_contracts
            if isinstance(c, dict)
        )
        return FutureChain(
            underlying=underlying,
            exchange=dhan_exchange,
            expiries=tuple(str(e) for e in expiries),
            contracts=contracts,
        )

    def funds(self) -> Balance:
        return self._conn.portfolio.get_balance()

    def positions(self) -> list[Position]:
        return self._conn.portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        return self._conn.portfolio.get_holdings()

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
            "depth_200_max_instruments_per_connection": DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION,
        }

    def capabilities(self) -> BrokerCapabilities:
        """Return Dhan broker capability matrix (single source of truth)."""
        from brokers.dhan.config.capabilities import dhan_capabilities

        return dhan_capabilities()

    def list_capabilities(self):
        """BrokerAdapter-compatible capability descriptor (session kernel)."""
        from brokers.common.broker_capabilities import CapabilityDescriptor

        return CapabilityDescriptor.build(self.capabilities(), frozenset())

    def search(self, query: str) -> list[dict]:
        return self._conn.instruments.search(query)

    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        The *on_tick* callback receives a canonical
        :class:`domain.Quote` object.  Broker-specific
        ``security_id`` values are never exposed to the caller — mapping is
        internal to the connection.
        """
        return self._conn.subscription_engine.subscribe_market(
            symbol, exchange, mode=mode, on_tick=on_tick
        )

    def unstream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream for *symbol* on *exchange*."""
        self._conn.subscription_engine.unsubscribe_market(symbol, exchange, on_tick=on_tick)

    # ── Parallel Data Fetching ──────────────────────────────────────

    def ltp_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Decimal]:
        """Fetch LTP for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_ltp(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Quote]:
        """Fetch quotes for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_quote(symbols, exchange)

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Fetch history for multiple symbols in parallel.

        Routes through the shared ``batch_execute`` helper (same engine Upstox
        uses) so both brokers share one parallel-fetch implementation.
        """
        from infrastructure.batch_executor import batch_execute

        per_symbol = batch_execute(
            symbols,
            lambda sym: self.history(sym, exchange, timeframe, lookback_days),
            max_workers=5,
            on_error=lambda sym, exc: logger.debug("history_batch_future_failed: %s", exc),
        )
        frames = [df for df in per_symbol.values() if not df.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def create_wire_adapter(connection: DhanConnection | DhanWireAdapter) -> DhanWireAdapter:
    if isinstance(connection, DhanWireAdapter):
        return connection
    return DhanWireAdapter(connection)


__all__ = [
    "DhanBrokerGateway",
    "DhanWireAdapter",
    "create_wire_adapter",
]

# Backward compatibility for old tests
DhanBrokerGateway = DhanWireAdapter
