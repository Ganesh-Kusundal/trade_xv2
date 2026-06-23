"""UpstoxBrokerGateway — thin sync facade delegating to UpstoxBroker adapters.

This class acts as a facade, delegating all operations to specialized adapters:
- MarketDataAdapter: HTTP market data (LTP, Quote, Depth)
- HistoricalAdapter: Historical candle fetching
- SymbolResolverAdapter: Instrument key resolution
- StreamManagerAdapter: WebSocket stream management
- OrderAdapter: Order placement and cancellation
- PortfolioAdapter: Portfolio, positions, holdings, funds

Thread Safety:
    All adapters are thread-safe. The facade itself is stateless except for
    delegating to the StreamManagerAdapter which manages subscription state.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from domain import (
    Balance,
    ExchangeSegment,
    FutureChain,
    OptionChain,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from infrastructure.event_bus import EventBus
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from brokers.upstox.adapters import (
    HistoricalAdapter,
    MarketDataAdapter,
    OrderAdapter,
    PortfolioAdapter,
    StreamManagerAdapter,
    SymbolResolverAdapter,
)
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.extended import UpstoxExtendedCapabilities

logger = logging.getLogger(__name__)


class UpstoxBrokerGateway(BatchFetchMixin, MarketDataGateway):
    """Unified Upstox broker API. All calls delegate to UpstoxBroker adapters.
    
    This facade provides a clean public API while internally delegating to
    specialized adapter classes for each responsibility area.
    
    Thread Safety:
        All delegated operations are thread-safe. Stream management uses
        internal locking in StreamManagerAdapter.
    
    Example::
    
        gateway = UpstoxBrokerGateway(broker)
        gateway.load_instruments()
        ltp = gateway.ltp("RELIANCE", "NSE")
        response = gateway.place_order("RELIANCE", "NSE", "BUY", 1)
    """

    def __init__(self, broker: UpstoxBroker):
        """Initialize gateway with broker facade and create adapters.

        Args:
            broker: UpstoxBroker instance with all underlying adapters initialized
        """
        self._broker = broker

        # Initialize specialized adapters
        self._market_data = MarketDataAdapter(broker)
        self._historical = HistoricalAdapter(broker)
        self._symbol_resolver = SymbolResolverAdapter(broker)
        self._stream_manager = StreamManagerAdapter(broker, broker.instrument_resolver)
        self._order_adapter = OrderAdapter(broker)
        self._portfolio = PortfolioAdapter(broker)

        # Broker-agnostic options facade for CLI / tests.
        from brokers.common.options.gateway_facade import GatewayOptionsFacade
        # The facade adapter is only constructed when the broker exposes an
        # ``options`` attribute — tests that build a MagicMock with
        # ``spec=UpstoxBroker`` (which doesn't list ``options``) still
        # construct successfully.
        options_attr = getattr(self._broker, "options", None)
        if options_attr is not None:
            self.options = GatewayOptionsFacade(
                options_attr, exchange_normalize=_upstox_normalize_exchange
            )


    # ── Backward compatibility properties (for tests accessing internals) ──

    @property
    def _stream_registry(self) -> dict:
        """Access stream registry from StreamManagerAdapter (backward compat)."""
        return self._stream_manager._stream_registry

    @property
    def _stream_lock(self):
        """Access stream lock from StreamManagerAdapter (backward compat)."""
        return self._stream_manager._stream_lock


    # ── Market Data (ABC-aligned) ─────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Fetch last traded price for a symbol.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            
        Returns:
            Last traded price as Decimal
        """
        key = self._symbol_resolver.resolve_key(symbol, exchange)
        return self._market_data.get_ltp(symbol, exchange, key)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Fetch full quote with OHLCV for a symbol.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            
        Returns:
            Quote dataclass with OHLCV data
        """
        key = self._symbol_resolver.resolve_key(symbol, exchange)
        return self._market_data.get_quote(symbol, exchange, key)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Fetch order book depth for a symbol.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            
        Returns:
            MarketDepth with bid/ask levels
        """
        key = self._symbol_resolver.resolve_key(symbol, exchange)
        return self._market_data.get_depth(symbol, exchange, key)

    def get_orderbook(self) -> list[Order]:
        """Fetch current order book.
        
        Returns:
            List of Order dataclasses
        """
        return self._portfolio.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        """Get today's trade book from the Upstox V2 trades-for-day endpoint.
        
        Returns:
            List of Trade dataclasses
        """
        return self._portfolio.get_trades()

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
        """Load instrument definitions from cache or download.
        
        Args:
            source: Optional path to instrument file. If not provided,
                   uses cached file or downloads from Upstox.
        """
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
        """Disconnect from broker and cleanup resources."""
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
        """Fetch historical candle data.
        
        Args:
            symbol: Single symbol or list of symbols
            exchange: Exchange segment
            timeframe: Candle timeframe (e.g., "1D", "5MIN", "1H")
            lookback_days: Number of days to look back
            from_date: Optional start date (YYYY-MM-DD)
            to_date: Optional end date (YYYY-MM-DD)
            
        Returns:
            DataFrame with OHLCV data
        """
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        to_str = to_date or str(to_d)
        from_str = from_date or str(from_d)
        tf = timeframe.upper() if timeframe else "1D"
        
        # Resolve timeframe to V3 interval
        unit, interval = HistoricalAdapter.resolve_timeframe(tf)

        if isinstance(symbol, str):
            return self._fetch_history(symbol, exchange, from_str, to_str, unit, interval)
        frames = []
        for sym in symbol:
            df = self._fetch_history(sym, exchange, from_str, to_str, unit, interval)
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _fetch_history(
        self,
        symbol: str,
        exchange: str,
        from_date: str,
        to_date: str,
        unit: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch historical candles for a single symbol.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            unit: Time unit (minutes, hours, days)
            interval: Interval value
            
        Returns:
            DataFrame with OHLCV data
        """
        key = self._symbol_resolver.resolve_key(symbol, exchange)
        return self._historical.fetch_candles(
            symbol, exchange, key, from_date, to_date, unit, interval
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get the option chain for an underlying."""
        if expiry is None:
            expiries = self._broker.options.get_expiries(underlying, exchange)
            if not expiries:
                return OptionChain(underlying=underlying, exchange=exchange, expiry="")
            expiry = expiries[0]
        from brokers.common.options.chain_normalizer import upstox_chain_to_canonical
        if hasattr(self._broker.options, "get_option_chain_with_meta"):
            result = self._broker.options.get_option_chain_with_meta(
                underlying, exchange, expiry
            )
            if isinstance(result, tuple) and len(result) == 3:
                contracts, raw_rows, _body = result
                return upstox_chain_to_canonical(
                    contracts, raw_rows, underlying, exchange, expiry
                )
        contracts = self._broker.options.get_option_chain(underlying, exchange, expiry)
        if not isinstance(contracts, list):
            return OptionChain(underlying=underlying, exchange=exchange, expiry=expiry)
        return upstox_chain_to_canonical(
            contracts, None, underlying, exchange, expiry
        )

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        """Get the future chain for an underlying.
        
        Raises:
            NotImplementedError: Upstox future chain is not supported
        """
        raise NotImplementedError(
            "Upstox future chain is not supported. Use Dhan for future chains."
        )

    def funds(self) -> Balance:
        """Fetch account fund limits.
        
        Returns:
            Balance dataclass with available margin
        """
        return self._portfolio.get_funds()

    def positions(self) -> list[Position]:
        """Fetch all positions.
        
        Returns:
            List of Position dataclasses
        """
        return self._portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        """Fetch all holdings.
        
        Returns:
            List of Holding dataclasses
        """
        return self._portfolio.get_holdings()

    def trades(self) -> list[Trade]:
        """Fetch trade book.
        
        Returns:
            List of Trade dataclasses
        """
        return self.get_trade_book()

    def describe(self) -> dict:
        """Get broker description metadata.
        
        Returns:
            Dict with broker capabilities and status
        """
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
        """Return Upstox broker capability matrix.
        
        Returns:
            BrokerCapabilities with supported features
        """
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
            # Order life-cycle
            amo=True,
            # Advanced order types
            slice_orders=True,
            conditional_triggers=True,
            # Risk management
            market_protection=True,
            # Investment capabilities
            ipo=True,
            mutual_funds=True,
            fundamentals=True,
            payments=True,
            # Account management
            user_profile=True,
            convert_position=True,
            trade_pnl=True,
            exit_all=True,
        )

    def search(self, query: str) -> list[dict]:
        """Search for instruments by query string.
        
        Args:
            query: Search query (symbol or name fragment)
            
        Returns:
            List of matching instrument dicts (max 20)
        """
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

        Thread-safe: uses ``_stream_lock`` to prevent race conditions during
        connect + subscribe. Callbacks are deduplicated via ``_stream_registry``
        so the same *on_tick* is not registered twice for the same instrument.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"RELIANCE"``)
            exchange: Exchange string (e.g. ``"NSE"``)
            mode:     Subscription mode — ``"ltpc"`` | ``"full"`` | ``"option_greeks"``
            on_tick:  Callable receiving a :class:`Quote` (or raw dict on
                      resolution failure)
        """
        return self._stream_manager.subscribe(symbol, exchange, mode, on_tick)

    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream.

        Removes the *on_tick* listener and SDK subscription. If *on_tick*
        is ``None``, removes ALL listeners for the instrument.

        Args:
            symbol:   Symbol to unsubscribe from.
            exchange: Exchange string.
            on_tick:  The callback to remove. ``None`` removes all.
        """
        self._stream_manager.unsubscribe(symbol, exchange, on_tick)

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
        is_amo: bool = False,
        transport_only: bool = False,
    ) -> OrderResponse:
        """Place an order via Upstox.

        Builds a canonical :class:`OrderRequest` and delegates to the
        order-command adapter, which handles instrument resolution,
        risk checks, idempotency, and payload construction.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`brokers.common.correlation.with_correlation`)
        is used for tracing.
        """
        return self._order_adapter.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
            is_amo=is_amo,
            transport_only=transport_only,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via Upstox.

        Returns:
            :class:`OrderResponse` with ``success`` reflecting the
            broker's response. Network/auth errors are reported as
            ``success=False`` with a diagnostic error code; this method
            never raises.
        """
        return self._order_adapter.cancel_order(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an order via Upstox V3 API."""
        from domain.entities import OrderResponse

        try:
            result = self._order_adapter.modify_order(order_id, **changes)
            if isinstance(result, dict) and result.get("status") == "success":
                return OrderResponse.ok(order_id=order_id, message="Order modified")
            message = result.get("message", "modify failed") if isinstance(result, dict) else "modify failed"
            return OrderResponse.fail(message)
        except Exception as exc:
            return OrderResponse.fail(str(exc))

    # ── Backward compatibility for internal methods (used by tests) ──

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote | dict[str, Any]:
        """Translate raw tick to Quote (backward compatibility for tests).
        
        Delegates to TickTranslatorAdapter via StreamManagerAdapter.
        
        Args:
            raw: Raw tick payload
            
        Returns:
            Quote or raw dict
        """
        return self._stream_manager._translate_tick_to_quote(raw)

    @staticmethod
    def _canonical_symbol_for_defn(
        defn: Any,
        fallback_key: str = "",
    ) -> str:
        """Derive canonical symbol from definition (backward compatibility).
        
        Args:
            defn: Instrument definition
            fallback_key: Fallback instrument key
            
        Returns:
            Canonical symbol string
        """
        from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter
        return TickTranslatorAdapter._canonical_symbol_for_defn(defn, fallback_key)


def _upstox_normalize_exchange(symbol: str, exchange: str) -> str:
    """Translate a generic exchange string into the Upstox segment form.

    CLI callers pass ``"INDEX"`` for index underlyings; the options adapter
    normalizes this to ``NSE_INDEX`` (or ``BSE_INDEX``) internally. The
    facade just passes through; the adapter handles segment mapping.
    """
    return exchange
