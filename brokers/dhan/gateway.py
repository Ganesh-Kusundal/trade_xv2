"""BrokerGateway — thin sync facade delegating to DhanConnection ports."""

from __future__ import annotations

import contextlib
import logging
import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.capabilities import dhan_capabilities
from brokers.common.dtos import BrokerOrderPayload
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway, ObservabilityProvider
from brokers.dhan.connection import DhanConnection
from brokers.dhan.exceptions import OrderError
from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT
from domain import (
    Balance,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)
from domain.exchange_segments import parse_segment
from domain.symbols import normalize_symbol
from infrastructure.observability.tracing import trace_operation

logger = logging.getLogger(__name__)


class BrokerGateway(BatchFetchMixin, MarketDataGateway, ObservabilityProvider):
    """Unified broker API. All calls delegate to connection adapters.

    Implements both MarketDataGateway (broker-agnostic contract) and
    ObservabilityProvider (canonical observability data exposure).
    """

    def __init__(self, connection: DhanConnection):
        self._conn = connection
        self._stream_lock = threading.Lock()
        # Deprecated: use connection.subscription_engine (kept for test backward compat)
        self._stream_registry: dict[tuple[str, str], list[Any]] = {}
        self._wrapper_registry: dict[tuple[str, str], list[tuple[Any, Any]]] = {}
        self._subscription_modes: dict[tuple[str, str], str] = {}
        # Broker-agnostic options facade — CLI/tests use ``gateway.options``.
        from brokers.common.options.gateway_facade import GatewayOptionsFacade

        self.options = GatewayOptionsFacade(
            self._conn.options,
            exchange_normalize=_dhan_normalize_exchange,
        )

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

    @trace_operation("dhan_gateway.place_order")
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
        transport_only: bool = False,
    ) -> OrderResponse:
        """Place an order with explicit parameters matching MarketDataGateway ABC.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`infrastructure.correlation.with_correlation`)
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
                from infrastructure.correlation import get_current_correlation_id

                correlation_id = get_current_correlation_id()
            except ImportError:
                pass

        exchange_segment = parse_segment(exchange)
        if exchange_segment is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")
        request = BrokerOrderPayload(
            symbol=symbol,
            exchange=exchange,
            exchange_segment=exchange_segment,
            transaction_type=Side(side.upper()),
            quantity=quantity,
            price=price,
            trigger_price=trigger_price if trigger_price > Decimal("0") else None,
            order_type=OrderType(order_type.upper()),
            product_type=ProductType(product_type.upper()),
            validity=Validity(validity.upper()),
            correlation_id=correlation_id,
            transport_only=transport_only,
        )
        try:
            order = self._conn.orders.place_order(request)
            status = OrderStatus.OPEN
            with contextlib.suppress(AttributeError, ValueError):
                status = OrderStatus(order.status.value.upper())
            return OrderResponse.ok(
                order_id=order.order_id,
                message="Order placed",
                status=status,
            )
        except OrderError as exc:
            return OrderResponse.fail(str(exc))

    @trace_operation("dhan_gateway.cancel_order")
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order with post-cancellation verification.

        H1 Critical Fix: After sending cancel request, verifies order actually
        reached cancelled state. Detects race condition where order was filled
        between cancel send and response.

        Returns:
            OrderResponse with success=True if cancelled, or
            OrderResponse.fail with error_code="ALREADY_EXECUTED" if order
            was already filled before cancel could complete.
        """
        # Step 1: Send cancel request
        response = self._conn.orders.cancel_order(order_id)

        # Step 2: Post-cancellation verification (H1 fix)
        if response.success:
            order = self.get_order(order_id)
            if order and order.status in (OrderStatus.FILLED,):
                return OrderResponse.fail(
                    message=f"Order {order_id} was already filled before cancel completed",
                    status=OrderStatus.FILLED,
                )

        return response

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID via direct lookup.

        Uses the OrdersAdapter.get_order() method which calls
        GET /orders/{order_id} directly, avoiding a full orderbook
        fetch. This halves API calls in cancel_order() verification.

        H1 Critical Fix: Enables post-cancellation verification by allowing
        lookup of individual orders.

        Performance: O(1) single-order fetch instead of O(n) orderbook scan.

        Args:
            order_id: Broker order ID to look up

        Returns:
            Order if found, None if not in orderbook or on error
        """
        try:
            return self._conn.orders.get_order(order_id)
        except Exception as exc:
            logger.warning(
                "get_order_failed",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return None

    @trace_operation("dhan_gateway.modify_order")
    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        from domain.entities import OrderResponse

        try:
            order = self._conn.orders.modify_order(order_id, **changes)
            return OrderResponse.ok(
                order_id=order.order_id, message="Order modified", status=order.status
            )
        except Exception as exc:
            return OrderResponse.fail(str(exc))

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

    def _complete_depth_snapshot(
        self,
        ws_depth: MarketDepth | None,
        symbol: str,
        exchange: str,
    ) -> MarketDepth:
        """Merge WebSocket depth with REST fallback for any missing side."""
        needs_rest = ws_depth is None or not ws_depth.bids or not ws_depth.asks
        rest: MarketDepth | None = None
        if needs_rest:
            rest = self._conn.market_data.get_depth(symbol, exchange)

        if ws_depth is None:
            return rest  # type: ignore[return-value]

        bids = ws_depth.bids if ws_depth.bids else (rest.bids if rest else [])
        asks = ws_depth.asks if ws_depth.asks else (rest.asks if rest else [])

        return MarketDepth(
            symbol=symbol,
            bids=list(bids),
            asks=list(asks),
            depth_type=ws_depth.depth_type,
            timestamp=ws_depth.timestamp or (rest.timestamp if rest else None),
        )

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
            raise ValueError(f"Depth 20 only supported for NSE segments, got: {exchange}")

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

        # Register the caller's callback.
        if on_depth is not None:
            feed.on_depth(on_depth)

        feed.register_symbol(sid_int, symbol)

        # Start the WebSocket if it's not running yet.
        if not feed.is_running:
            feed.start()

        cached = feed.latest_depth(sid_int)
        result = self._complete_depth_snapshot(cached, symbol, exchange)
        if cached is not None:
            logger.debug(
                "depth_20_from_websocket",
                extra={
                    "symbol": symbol,
                    "exchange": exchange,
                    "depth_type": result.depth_type,
                    "bid_levels": len(result.bids),
                    "ask_levels": len(result.asks),
                    "rest_merged": bool(cached and (not cached.bids or not cached.asks)),
                },
            )
            return result

        logger.debug(
            "depth_20_fallback_to_rest",
            extra={
                "symbol": symbol,
                "exchange": exchange,
                "reason": "no websocket data received yet",
            },
        )
        return result

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
            raise ValueError(f"Depth 200 only supported for NSE segments, got: {exchange}")

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
            # Already has a subscription — validate it's the same instrument.
            existing = feed.subscriptions[0][1] if feed.subscriptions else None
            if existing and existing != sid_str:
                raise ValueError(
                    f"Depth 200 feed already subscribed to security_id {existing}. "
                    f"Create a new gateway connection to stream a different instrument."
                )

        # Register the caller's callback.
        if on_depth is not None:
            feed.on_depth(on_depth)

        feed.register_symbol(int(sid_str), symbol)

        # Start the WebSocket if it's not running yet.
        if not feed.is_running:
            feed.start()

        cached = feed.latest_depth()
        return self._complete_depth_snapshot(cached, symbol, exchange)

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        from brokers.dhan.exceptions import InstrumentNotFoundError
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        to_str = to_date or str(to_d)
        from_str = from_date or str(from_d)
        tf = timeframe.upper() if timeframe else "1D"
        if isinstance(symbol, str):
            try:
                return self._conn.historical.get_historical(symbol, exchange, from_str, to_str, tf)
            except InstrumentNotFoundError:
                logger.warning("history: instrument not found: %s/%s", symbol, exchange)
                return pd.DataFrame()
        frames = []
        for sym in symbol:
            try:
                df = self._conn.historical.get_historical(sym, exchange, from_str, to_str, tf)
                frames.append(df)
            except InstrumentNotFoundError:
                logger.warning("history: instrument not found: %s/%s", sym, exchange)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get option chain. Delegates MCX-specific expiry lookup to extended."""
        return OptionChain.from_dict(self.extended.get_option_chain(underlying, exchange, expiry))

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        from config.indices import INDEX_TO_FNO_EXCHANGE

        # Index futures use the mapped exchange; stock futures always trade on NFO.
        # If a caller passes exchange="NSE" for a stock like RELIANCE, remap to NFO.
        dhan_exchange = INDEX_TO_FNO_EXCHANGE.get(underlying.upper(), None)
        if dhan_exchange is None:
            # Not an index — it's a stock. Stock F&O always trades on NFO.
            dhan_exchange = "NFO" if exchange.upper() in ("NSE", "BSE") else exchange
        contracts = self._conn.futures.get_contracts(underlying, dhan_exchange)
        expiries = self._conn.futures.get_expiries(underlying, dhan_exchange)
        chain = []
        for c in contracts:
            chain.append(
                {
                    "expiry": c.get("expiry", ""),
                    "symbol": c.get("symbol", ""),
                    "lot_size": c.get("lot_size", 1),
                    "underlying": c.get("underlying", underlying),
                }
            )
        return FutureChain.from_dict(
            {
                "underlying": underlying,
                "exchange": dhan_exchange,
                "expiries": expiries,
                "contracts": chain,
            }
        )

    def get_balance(self) -> Balance:
        """Return current account balance (fund limits).

        Delegates to the portfolio adapter's ``get_balance()`` which
        calls ``GET /fundlimit`` on the Dhan API.
        """
        return self._conn.portfolio.get_balance()

    def funds(self) -> Balance:
        """Alias for :meth:`get_balance` — backward-compatible contract name."""
        return self.get_balance()

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
        return dhan_capabilities()

    def search(self, query: str) -> list[dict]:
        results = []
        q = normalize_symbol(query)
        for inst in self._conn.instruments.all_instruments():
            if q in inst.symbol.upper() or q in (inst.canonical_symbol or "").upper():
                results.append(
                    {
                        "symbol": inst.symbol,
                        "exchange": inst.exchange.value,
                        "type": inst.instrument_type.value,
                        "security_id": inst.security_id,
                        "name": inst.canonical_symbol,
                    }
                )
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

        Delegates to :class:`SubscriptionEngine` — the single source of truth
        for instrument subscriptions and callback multiplexing.
        """
        with self._stream_lock:
            return self._conn.subscription_engine.subscribe_market(
                symbol, exchange, mode, on_tick
            )

    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream."""
        with self._stream_lock:
            self._conn.subscription_engine.unsubscribe_market(symbol, exchange, on_tick)

    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to account-wide order updates via the shared order stream."""
        with self._stream_lock:
            return self._conn.subscription_engine.subscribe_order(on_order)

    def unstream_order(self, on_order: Any | None = None) -> None:
        """Remove an order-update callback from the shared order stream."""
        with self._stream_lock:
            self._conn.subscription_engine.unsubscribe_order(on_order)

    # ── Parallel Data Fetching ──────────────────────────────────────

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Fetch LTP for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_ltp(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Fetch quotes for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_quote(symbols, exchange)

    # history_batch inherited from BatchFetchMixin (parallel single-item history calls)

    # -----------------------------------------------------------------------
    # ObservabilityProvider Implementation
    # -----------------------------------------------------------------------

    def get_connection_status(self) -> dict[str, bool]:
        """Return connection status for Dhan WebSocket streams.

        Implements ObservabilityProvider protocol to expose connection
        status without exposing private attributes to CLI layer.
        """
        status: dict[str, bool | str | float | None] = {}
        mf = getattr(self._conn, "market_feed", None)
        if mf is not None:
            status["market_feed"] = mf.is_connected
            with contextlib.suppress(Exception):
                health = mf.health()
                metrics = health.metrics or {}
                status["market_feed_stale"] = bool(metrics.get("is_stale", False))
                status["connection_lock_acquired"] = bool(
                    metrics.get("connection_lock_acquired", False)
                )
                status["connection_blocked_by_lock"] = bool(
                    metrics.get("connection_blocked_by_lock", False)
                )
                status["next_connect_allowed_at"] = metrics.get("next_connect_allowed_at")

        os_ = getattr(self._conn, "order_stream", None)
        if os_ is not None:
            status["order_stream"] = os_.is_connected

        d20 = getattr(self._conn, "depth_20_feed", None)
        if d20 is not None:
            connected = getattr(d20, "is_connected", None)
            if callable(connected):
                status["depth_20"] = bool(connected())
            else:
                status["depth_20"] = bool(getattr(d20, "_is_connected", False))

        d200 = getattr(self._conn, "depth_200_feed", None)
        if d200 is not None:
            connected = getattr(d200, "is_connected", None)
            if callable(connected):
                status["depth_200"] = bool(connected())
            else:
                status["depth_200"] = bool(getattr(d200, "_is_connected", False))

        engine = getattr(self._conn, "subscription_engine", None)
        if engine is not None:
            status["has_active_subscriptions"] = engine.subscription_count() > 0

        return status

    def get_circuit_breaker_states(self) -> dict[str, int]:
        """Return Dhan client circuit breaker states.

        Maps CircuitState enum to int: 0=CLOSED, 1=OPEN, 2=HALF_OPEN.
        Implements ObservabilityProvider protocol.

        Delegates to the connection's public ``circuit_breaker_states``
        property so the gateway never touches private ``_client`` attributes.
        """
        return self._conn.circuit_breaker_states

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics from Dhan connection.

        Implements ObservabilityProvider protocol.

        Delegates to the connection's public ``token_refresh_metrics``
        property so the gateway never touches private ``_token_scheduler``.
        """
        return self._conn.token_refresh_metrics


def _dhan_normalize_exchange(symbol: str, exchange: str) -> str:
    """Translate a generic exchange string into the Dhan-canonical form.

    Dhan option-chain calls accept ``"INDEX"`` (per integration tests) and
    ``"NSE"`` / ``"BSE"``. The integration suite uses ``"INDEX"`` for index
    underlyings (NIFTY, BANKNIFTY); we keep that convention.
    """
    from config.indices import dhan_index_exchange, is_index

    if is_index(symbol):
        return dhan_index_exchange(symbol) or exchange
    return exchange
