"""Dhan wire adapter — sanctioned transport boundary over DhanConnection."""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from domain.capabilities.broker_capabilities import BrokerCapabilities
from brokers.common.capabilities_validator import enforce_gateway_capabilities
from brokers.common.streaming import DepthStreamHandle
from brokers.common.wire_base import BaseWireAdapter
from brokers.providers.dhan.config.capabilities import DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION
from brokers.providers.dhan.streaming.connection import DhanConnection
from domain.entities import (
    Balance,
    DepthKind,
    MarketDepth,
    OrderResponse,
    Quote,
)
from domain.constants import DEFAULT_DERIVATIVES_EXCHANGE, DEFAULT_EXCHANGE
from domain.entities import (
    Holding,
    Order,
    Position,
    Trade,
)
from domain.entities.options import FutureChain, OptionChain
from domain.orders.requests import OrderRequest
from domain.ports.broker_adapter import BrokerAdapter

logger = logging.getLogger(__name__)


class DhanWireAdapter(BaseWireAdapter, BrokerAdapter):
    """Unified Dhan broker API — all calls delegate to connection adapters."""

    # BrokerAdapter port requires a stable broker_id attribute.
    broker_id = "dhan"

    def __init__(self, connection: DhanConnection):
        self._conn = connection
        self._stream_lock = threading.Lock()
        enforce_gateway_capabilities(self)

    @property
    def connection(self) -> DhanConnection:
        return self._conn

    def _transport_connected(self) -> bool:
        """Authenticated + transport alive.

        A REST-only session (no WS feed yet) is connected when the HTTP client
        holds a usable access token. If a market feed exists, its socket state
        is authoritative.
        """
        conn = self._conn
        client = getattr(conn, "_client", None)
        rest_ok = bool(client is not None and (getattr(client, "access_token", None) or "").strip())
        feed = getattr(conn, "market_feed", None) or getattr(conn, "_market_feed", None)
        if feed is not None and hasattr(feed, "is_connected"):
            return bool(feed.is_connected) or rest_ok
        return rest_ok

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

        Returns a :class:`~brokers.providers.dhan.extended.DhanExtendedCapabilities`
        instance with broker-specific methods (super orders, forever orders,
        conditional triggers, ledger, user profile, IP management, EDIS,
        option/futures listing, order validation).
        """
        from brokers.providers.dhan.extended import DhanExtendedCapabilities

        return DhanExtendedCapabilities(self._conn)

    # ── Order shortcuts ──

    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order via the typed ``OrderRequest``.

        If ``correlation_id`` is not set on the request, the current thread's
        active correlation ID is used for automatic end-to-end tracing.
        """
        from brokers.services._session import check_live_actionable

        check_live_actionable(self.broker_id)

        if not request.correlation_id:
            try:
                from domain.correlation import get_current_correlation_id

                object.__setattr__(request, "correlation_id", get_current_correlation_id())
            except ImportError:
                pass

        from brokers.common.order_wire import order_request_to_payload
        from domain.models.dtos import BrokerOrderPayload

        payload = order_request_to_payload(request, "dhan")
        # Transport-only metadata: extract is_amo from BrokerOrderPayload if present,
        # otherwise default to False.
        is_amo = False
        if isinstance(request, BrokerOrderPayload):
            is_amo = request.provider_metadata.get("is_amo", False)
        payload.provider_metadata["is_amo"] = is_amo
        return self._conn.orders.place_order(payload)

    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._conn.orders.cancel_order(order_id)

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
            from brokers.common.transport_errors import map_transport_exception

            mapped = map_transport_exception(e)
            logger.warning(
                "get_order_failed",
                extra={"order_id": order_id, "error": str(mapped), "error_type": type(mapped).__name__},
            )
            raise mapped from e

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
            # (see brokers.providers.dhan.websocket._helpers._transform_depth), so
            # subscribe there instead of a one-shot REST snapshot. Matches
            # Upstox's levels=5, which is a genuinely live "full" mode stream.
            from decimal import Decimal as _Decimal

            from domain.entities import DepthLevel

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
                on_depth(
                    MarketDepth(
                        symbol=symbol,
                        bids=bids,
                        asks=asks,
                        depth_type=DepthKind.DEPTH_5,
                    )
                )

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
        symbol: str,
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
        return self._conn.historical.get_historical(symbol, exchange, from_str, to_str, tf)

    def get_expired_options_data(self, **kwargs: Any) -> Any:
        """Rolling expired index options (NFO OPTIDX)."""
        return self.extended.data.get_expired_options_data(**kwargs)

    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        """Get option chain. Delegates MCX-specific expiry lookup to data sub-facade."""
        from brokers.providers.dhan.data_capabilities import DhanDataCapabilities
        from domain.entities.options import OptionChain

        raw = DhanDataCapabilities(self._conn).get_option_chain(underlying, exchange, expiry)
        if isinstance(raw, OptionChain):
            return raw
        if isinstance(raw, dict):
            data = dict(raw)
            data.setdefault("underlying", underlying)
            data.setdefault("exchange", exchange)
            if expiry and not data.get("expiry"):
                data["expiry"] = expiry
            return OptionChain.from_dict(data)
        return OptionChain(underlying=underlying, exchange=exchange, expiry=expiry or "")

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
        from brokers.providers.dhan.config.capabilities import dhan_capabilities

        return dhan_capabilities()

    def list_capabilities(self):
        """BrokerAdapter-compatible capability descriptor (session kernel)."""
        from domain.capabilities.broker_capabilities import CapabilityDescriptor

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
        with self._stream_lock:
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
        with self._stream_lock:
            self._conn.subscription_engine.unsubscribe_market(
                symbol, exchange, on_tick=on_tick
            )

    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to account-wide order updates; distinct from market ``stream``."""
        return self._conn.subscription_engine.subscribe_order(on_order)

    def unstream_order(self, on_order: Any | None = None) -> None:
        """Remove an order-update callback (or all if *on_order* is None)."""
        self._conn.subscription_engine.unsubscribe_order(on_order)

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
    "DhanWireAdapter",
    "create_wire_adapter",
]
