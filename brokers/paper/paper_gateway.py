"""Paper trading gateway — simulated broker for testing and development."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timezone
import asyncio
from decimal import Decimal
import uuid
from typing import Any

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.broker_port import (
    BrokerHealthSnapshot,
    BrokerStreamHandle,
    BrokerStreamPlan,
    CommonBrokerGateway,
    HistoricalBarRequest,
    QuotaToken,
)
from brokers.common.capabilities import CapabilityDescriptor
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
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
from domain.constants.defaults import PAPER_INITIAL_CAPITAL
from domain.historical import HistoricalBar, InstrumentRef
from domain.provenance import DataProvenance, SourceIdentity
from domain.requests import ModifyOrderRequest, OrderRequest

from .paper_market_data import PaperMarketData
from .paper_orders import PaperOrders
from .paper_portfolio import PaperPortfolio


class PaperGateway(BatchFetchMixin, MarketDataGateway, CommonBrokerGateway):
    """Unified paper-trading API implementing both MarketDataGateway v1.0 and CommonBrokerGateway protocols.

    All market-data, order, and portfolio calls delegate to the
    corresponding adapter objects (``market_data``, ``orders``, ``portfolio``).

    Implements:
        - CommonBrokerGateway: Async protocol for modern infrastructure
        - Market Data: history, quote, ltp, depth, option_chain, future_chain, stream
        - Batch: ltp_batch, quote_batch, history_batch
        - Trading: place_order, cancel_order, modify_order, get_orderbook, get_trade_book
        - Portfolio: positions, holdings, funds, trades
        - Instrument: search, load_instruments
        - Lifecycle: describe, capabilities, close
    """

    def __init__(
        self,
        initial_capital: Decimal = PAPER_INITIAL_CAPITAL,
        *,
        order_manager: Any | None = None,
        position_manager: Any | None = None,
        trading_context: Any | None = None,
    ) -> None:
        # ``trading_context`` is a backward-compatible injection path; composition
        # roots should prefer explicit order_manager / position_manager.
        if trading_context is not None:
            order_manager = order_manager or getattr(trading_context, "order_manager", None)
            position_manager = position_manager or getattr(
                trading_context, "position_manager", None
            )
        self._trading_context = trading_context
        self._market_data = PaperMarketData()
        self._orders = PaperOrders(
            self._market_data,
            {},
            order_manager=order_manager,
            position_manager=position_manager,
        )
        self._portfolio = PaperPortfolio(self._orders, initial_capital)
        # Cache for CommonBrokerGateway capability descriptor
        self._capabilities_cache: CapabilityDescriptor | None = None

    @property
    def market_data(self) -> PaperMarketData:
        return self._market_data

    @property
    def orders(self) -> PaperOrders:
        return self._orders

    @property
    def trading_context(self) -> Any | None:
        return self._trading_context

    @property
    def portfolio(self) -> PaperPortfolio:
        return self._portfolio

    # =======================================================================
    # CommonBrokerGateway Protocol Implementation (Async)
    # =======================================================================

    @property
    def broker_id(self) -> str:
        """Canonical broker identifier for CommonBrokerGateway protocol."""
        return "paper"

    def list_capabilities(self) -> CapabilityDescriptor:
        """Return the broker's capability descriptor for CommonBrokerGateway protocol."""
        if self._capabilities_cache is None:
            self._capabilities_cache = CapabilityDescriptor.build(
                capabilities=self.capabilities(),
                extensions=frozenset(),  # Paper gateway has no extensions
            )
        return self._capabilities_cache

    def supports(self, feature: str) -> bool:
        """Shorthand for capability check."""
        return self.list_capabilities().capabilities.supports(feature)

    async def health(self) -> BrokerHealthSnapshot:
        """Return health snapshot for paper gateway - always healthy."""
        return BrokerHealthSnapshot(
            broker_id="paper",
            alive=True,
            auth_valid=True,
            error_rate=0.0,
            latency_p50=0.0,
            reason="",
        )

    # Trading methods (async) - Paper trading uses asyncio.to_thread
    # Note: Paper gateway is CPU-bound (simulation), so asyncio.to_thread is appropriate
    # The quota parameter is validated but not enforced (paper trading has no real limits)
    async def place_order(
        self,
        request: OrderRequest,
        *,
        quota: QuotaToken,
    ) -> OrderResponse:
        """Async place_order for CommonBrokerGateway protocol.
        
        Note: Paper gateway uses asyncio.to_thread since order simulation is CPU-bound.
        The quota token is validated for protocol compliance but not enforced.
        """
        # Validate quota token structure (protocol compliance)
        self._validate_quota(quota)
        
        # Map OrderRequest fields to sync place_order parameters
        side = request.transaction_type.value if hasattr(request.transaction_type, 'value') else str(request.transaction_type)
        order_type = request.order_type.value if hasattr(request.order_type, 'value') else str(request.order_type)
        product_type = request.product_type.value if hasattr(request.product_type, 'value') else str(request.product_type)
        validity = request.validity.value if hasattr(request.validity, 'value') else str(request.validity)
        
        # Use asyncio.to_thread for CPU-bound simulation
        return await asyncio.to_thread(
            self._sync_place_order,
            symbol=request.symbol,
            exchange=request.exchange,
            side=side,
            quantity=request.quantity,
            price=request.price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=request.trigger_price or Decimal("0"),
            correlation_id=request.correlation_id,
        )

    def _validate_quota(self, quota: QuotaToken) -> None:
        """Validate quota token structure for protocol compliance.
        
        Paper gateway doesn't enforce quota limits but validates the token structure
        to ensure protocol compliance with CommonBrokerGateway.
        """
        if not isinstance(quota, QuotaToken):
            raise TypeError(f"Expected QuotaToken, got {type(quota).__name__}")
        if not quota.broker_id:
            raise ValueError("QuotaToken must have a broker_id")
        if not quota.endpoint_class:
            raise ValueError("QuotaToken must have an endpoint_class")

    def _sync_place_order(self, *args, **kwargs) -> OrderResponse:
        """Internal sync place_order method that bypasses the async method."""
        # Call the original sync implementation
        order = self._orders.place_order(*args, **kwargs)
        return OrderResponse(
            success=True,
            order_id=order.order_id,
            message="Order filled (paper)",
            status=order.status,
        )

    async def cancel_order(
        self,
        order_id: str,
        *,
        quota: QuotaToken,
    ) -> OrderResponse:
        """Async cancel_order for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_cancel_order, order_id)

    def _sync_cancel_order(self, order_id: str) -> OrderResponse:
        """Internal sync cancel_order method."""
        # PaperOrders.cancel_order returns True if order was found and cancelled, False otherwise
        success = self._orders.cancel_order(order_id)
        
        # Try to get the order to check its status
        cancelled_order = self._orders.get_order(order_id)
        
        if success and cancelled_order:
            return OrderResponse(
                success=True,
                order_id=order_id,
                message="Order cancelled (paper)",
                status=OrderStatus.CANCELLED,
            )
        elif cancelled_order and cancelled_order.status == OrderStatus.FILLED:
            # Order was already filled, cannot cancel
            return OrderResponse(
                success=False,
                order_id=order_id,
                message=f"Order {order_id} was already filled before cancel completed",
                status=OrderStatus.FILLED,
            )
        else:
            return OrderResponse(
                success=False,
                order_id=order_id,
                message="Order not found",
                status=OrderStatus.REJECTED,
            )

    async def modify_order(
        self,
        request: ModifyOrderRequest,
        *,
        quota: QuotaToken,
    ) -> OrderResponse:
        """Async modify_order for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        # Map ModifyOrderRequest to existing modify_order kwargs
        # Note: PaperOrders.modify_order doesn't support product_type parameter
        changes = {}
        if request.quantity is not None:
            changes["quantity"] = request.quantity
        if request.price is not None:
            changes["price"] = request.price
        if request.trigger_price is not None:
            changes["trigger_price"] = request.trigger_price
        if request.order_type is not None:
            changes["order_type"] = request.order_type.value if hasattr(request.order_type, 'value') else str(request.order_type)
        if request.validity is not None:
            changes["validity"] = request.validity.value if hasattr(request.validity, 'value') else str(request.validity)
        # product_type is NOT passed to PaperOrders.modify_order as it doesn't support it
        
        return await asyncio.to_thread(self._sync_modify_order, request.order_id, changes)

    def _sync_modify_order(self, order_id: str, changes: dict) -> OrderResponse:
        """Internal sync modify_order method."""
        order = self._orders.modify_order(order_id, **changes)
        return OrderResponse(
            success=order is not None,
            order_id=order_id,
            message="Order modified (paper)" if order else "Order not found",
            status=order.status if order else None,
        )

    # Portfolio methods (async)
    async def get_positions(self, *, quota: QuotaToken) -> list[Position]:
        """Async get_positions for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_positions)

    def _sync_positions(self) -> list[Position]:
        """Internal sync positions method."""
        return self.positions()

    async def get_margins(self, *, quota: QuotaToken) -> Balance:
        """Async get_margins for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_funds)

    def _sync_funds(self) -> Balance:
        """Internal sync funds method."""
        return self.funds()

    async def get_orders(self, *, quota: QuotaToken) -> list[Order]:
        """Async get_orders for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_get_orderbook)

    def _sync_get_orderbook(self) -> list[Order]:
        """Internal sync get_orderbook method."""
        return self.get_orderbook()

    async def get_trades(self, *, quota: QuotaToken) -> list[Trade]:
        """Async get_trades for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_get_trade_book)

    def _sync_get_trade_book(self) -> list[Trade]:
        """Internal sync get_trade_book method."""
        return self.get_trade_book()

    # Market data methods (async)
    async def get_quote_snapshot(
        self,
        instrument: InstrumentRef,
        *,
        quota: QuotaToken,
    ) -> Quote:
        """Async get_quote_snapshot for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_quote, instrument.symbol, instrument.exchange)

    def _sync_quote(self, symbol: str, exchange: str) -> Quote:
        """Internal sync quote method."""
        return self.quote(symbol, exchange)

    async def get_depth_snapshot(
        self,
        instrument: InstrumentRef,
        *,
        quota: QuotaToken,
    ) -> MarketDepth:
        """Async get_depth_snapshot for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        return await asyncio.to_thread(self._sync_depth, instrument.symbol, instrument.exchange)

    def _sync_depth(self, symbol: str, exchange: str) -> MarketDepth:
        """Internal sync depth method."""
        return self.depth(symbol, exchange)

    # Historical data method (async)
    async def get_historical_bars(
        self,
        request: HistoricalBarRequest,
        *,
        quota: QuotaToken,
    ) -> Sequence[HistoricalBar]:
        """Async get_historical_bars for CommonBrokerGateway protocol.
        
        Note: Uses asyncio.to_thread for CPU-bound simulation.
        """
        self._validate_quota(quota)
        # Call existing sync history method
        df = self.history(
            symbol=request.instrument.symbol,
            exchange=request.instrument.exchange,
            timeframe=request.timeframe,
            from_date=request.from_date,
            to_date=request.to_date,
        )

        # Convert DataFrame to HistoricalBar sequence
        bars = []
        bar_index = 0
        for _, row in df.iterrows():
            timestamp = row["timestamp"]
            if pd.isna(timestamp):
                timestamp = pd.Timestamp.now(tz=timezone.utc)
            else:
                timestamp = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
                
            open_price = Decimal(str(row["open"])) if pd.notna(row["open"]) else Decimal("0")
            high = Decimal(str(row["high"])) if pd.notna(row["high"]) else Decimal("0") 
            low = Decimal(str(row["low"])) if pd.notna(row["low"]) else Decimal("0")
            close = Decimal(str(row["close"])) if pd.notna(row["close"]) else Decimal("0")
            volume = int(row["volume"]) if pd.notna(row["volume"]) else 0
            oi = int(row["oi"]) if pd.notna(row["oi"]) and row["oi"] != 0 else 0
            
            bar = HistoricalBar(
                instrument=request.instrument,
                timeframe=request.timeframe,
                event_time=timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                open_interest=oi,
                provenance=DataProvenance.now(
                    source=SourceIdentity(broker_id="paper", venue=request.instrument.exchange),
                    request_id=request.request_id,
                ),
                bar_index=bar_index,
                is_partial=False,
            )
            bars.append(bar)
            bar_index += 1
        return bars

    # Stream methods (async) - Paper implementation returns mock handles
    class _PaperBrokerStreamHandle:
        """Paper implementation of BrokerStreamHandle for CommonBrokerGateway protocol."""

        def __init__(self, session_id: str, broker_id: str = "paper"):
            self._session_id = session_id
            self._broker_id = broker_id
            self._connected = True

        @property
        def session_id(self) -> str:
            return self._session_id

        @property
        def broker_id(self) -> str:
            return self._broker_id

        async def disconnect(self) -> None:
            self._connected = False

        def is_connected(self) -> bool:
            return self._connected

    async def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        """Open a market data stream - paper implementation returns a mock handle."""
        return self._PaperBrokerStreamHandle(
            session_id=f"paper_market_{uuid.uuid4().hex[:8]}",
            broker_id="paper",
        )

    async def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        """Open an order stream - paper implementation returns a mock handle."""
        return self._PaperBrokerStreamHandle(
            session_id=f"paper_order_{uuid.uuid4().hex[:8]}",
            broker_id="paper",
        )

    # =======================================================================
    # Market Data (read-only)
    # =======================================================================

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        import hashlib
        from datetime import datetime, timedelta, timezone

        import numpy as np

        symbols = [symbol] if isinstance(symbol, str) else symbol
        n = lookback_days
        dates = [datetime.now(timezone.utc) - timedelta(days=n - i) for i in range(n)]

        rows = []
        for sym in symbols:
            seed = int(hashlib.sha256(sym.encode()).hexdigest()[:8], 16) % (2**31)
            np.random.seed(seed)
            base_price = 500.0 + np.random.uniform(0, 4500)
            close = base_price + np.cumsum(np.random.randn(n) * base_price * 0.02)
            high = close + abs(np.random.randn(n)) * base_price * 0.01
            low = close - abs(np.random.randn(n)) * base_price * 0.01
            open_ = close + np.random.randn(n) * base_price * 0.005
            volume = np.random.randint(10000, 500000, n).astype(float)

            for i in range(n):
                rows.append(
                    {
                        "timestamp": dates[i],
                        "open": round(open_[i], 2),
                        "high": round(high[i], 2),
                        "low": round(low[i], 2),
                        "close": round(close[i], 2),
                        "volume": int(volume[i]),
                        "oi": 0,
                        "symbol": sym,
                        "exchange": exchange,
                        "timeframe": timeframe,
                    }
                )

        return pd.DataFrame(rows)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        q = self._market_data.get_quote(symbol, exchange)
        return Quote(
            symbol=symbol,
            ltp=q.ltp,
            open=q.open,
            high=q.high,
            low=q.low,
            close=q.close,
            volume=q.volume,
            change=q.change,
            bid=q.bid,
            ask=q.ask,
            timestamp=q.timestamp,
        )

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._market_data.get_ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        d = self._market_data.get_depth(symbol, exchange)
        return MarketDepth(
            symbol=symbol,
            bids=list(d.bids),
            asks=list(d.asks),
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        import numpy as np

        base = float(self._market_data.get_ltp(underlying, "NSE"))
        strikes = [round(base + i * 50, 0) for i in range(-10, 11)]
        chain = []
        for strike in strikes:
            chain.append(
                {
                    "strike": strike,
                    "call": {"ltp": round(max(0, base - strike + np.random.uniform(5, 50)), 2)},
                    "put": {"ltp": round(max(0, strike - base + np.random.uniform(5, 50)), 2)},
                }
            )
        return OptionChain.from_dict(
            {
                "underlying": underlying,
                "exchange": exchange,
                "expiry": expiry or "2026-07-30",
                "strikes": chain,
            }
        )

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        import numpy as np

        base = float(self._market_data.get_ltp(underlying, "NSE"))
        from datetime import datetime, timedelta

        expiries = [
            (datetime.now() + timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(1, 4)
        ]
        contracts = []
        for exp in expiries:
            contracts.append(
                {
                    "expiry": exp,
                    "ltp": round(base * (1 + np.random.uniform(-0.02, 0.03)), 2),
                    "volume": int(np.random.randint(10000, 500000)),
                    "oi": int(np.random.randint(50000, 1000000)),
                    "change": round(np.random.uniform(-2, 2), 2),
                }
            )
        return FutureChain.from_dict(
            {
                "underlying": underlying,
                "exchange": exchange,
                "expiries": expiries,
                "contracts": contracts,
            }
        )

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        class _PaperStream:
            def connect(self):
                pass

            def disconnect(self):
                pass

            @property
            def is_connected(self):
                return False

        return _PaperStream()

    # =======================================================================
    # Trading
    # =======================================================================





    def seed_orders(self, orders: list[Order]) -> None:
        self._orders._orders = orders

    def seed_trades(self, trades: list[Trade]) -> None:
        self._orders._trades = trades

    def seed_positions(self, positions: dict[str, Position]) -> None:
        self._orders._positions = positions

    def seed_holdings(self, holdings: list[Holding]) -> None:
        self._portfolio._holdings = holdings

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID from the orderbook.

        H1 Critical Fix: Enables post-cancellation verification by allowing
        lookup of individual orders.

        Args:
            order_id: Paper order ID to look up

        Returns:
            Order if found, None if not in orderbook
        """
        return self._orders.get_order(order_id)



    def get_orderbook(self) -> list[Order]:
        return self._orders.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        return self._orders.get_trade_book()

    # =======================================================================
    # Portfolio
    # =======================================================================

    def positions(self) -> list[Position]:
        return self._portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        return self._portfolio.get_holdings()

    def funds(self) -> Balance:
        return self._portfolio.get_balance()

    def trades(self) -> list[Trade]:
        return self._orders.get_trade_book()

    # =======================================================================
    # Instrument
    # =======================================================================

    def search(self, query: str) -> list[dict]:
        return [{"symbol": query.upper(), "exchange": "NSE", "name": query.upper()}]

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        pass

    # =======================================================================
    # Lifecycle
    # =======================================================================

    def capabilities(self) -> BrokerCapabilities:
        from brokers.common.capabilities import (
            BrokerCapabilities,
            HistoricalWindowConstraint,
            RateLimitProfile,
            StreamLimitProfile,
        )

        return BrokerCapabilities(
            broker_id="paper",
            supports_place_order=True,
            supports_cancel_order=True,
            supports_modify_order=True,
            supports_historical_data=True,
            supports_intraday_history=True,
            supports_expired_options_history=True,
            supports_live_market_data=True,
            supports_depth=True,
            supports_depth_20_ws=True,
            supports_depth_200_ws=False,
            supports_option_chain=True,
            supports_polling_fallback=True,
            supports_order_stream=True,
            supports_portfolio_stream=False,
            supports_news=False,
            supports_fundamentals=False,
            supports_super_order=False,
            supports_forever_order=False,
            supports_native_slice_order=False,
            rate_limit_profiles=(
                RateLimitProfile(
                    endpoint_class="orders",
                    sustained_rps=1000.0,  # Paper trading has no real limits
                    burst_rps=2000.0,
                    min_interval_ms=0,  # No minimum interval for paper
                    cooldown_on_429_s=None,  # No rate limiting
                ),
                RateLimitProfile(
                    endpoint_class="quotes",
                    sustained_rps=1000.0,
                    burst_rps=2000.0,
                    min_interval_ms=0,
                    cooldown_on_429_s=None,
                ),
                RateLimitProfile(
                    endpoint_class="historical",
                    sustained_rps=1000.0,
                    burst_rps=2000.0,
                    min_interval_ms=0,
                    cooldown_on_429_s=None,
                ),
                RateLimitProfile(
                    endpoint_class="option_chain",
                    sustained_rps=1000.0,
                    burst_rps=2000.0,
                    min_interval_ms=0,
                    cooldown_on_429_s=None,
                ),
            ),
            historical_windows=(
                HistoricalWindowConstraint(
                    timeframe="1m",
                    max_lookback_days=3650,
                    max_chunk_days=365,
                    supports_expired_instruments=True,
                ),
                HistoricalWindowConstraint(
                    timeframe="1D",
                    max_lookback_days=3650,
                    max_chunk_days=365,
                ),
            ),
            stream_limits=StreamLimitProfile(
                max_connections=1,
                max_instruments_per_connection=1000,
                max_depth_levels=20,
                supported_stream_modes=frozenset({"LTP", "QUOTE", "FULL"}),
            ),
            latency_class="low",
            reliability_class="tier1",
            product_types=frozenset({"INTRADAY", "MARGIN", "CNC"}),
            order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
            max_batch_size=100,
        )

    def describe(self) -> dict:
        return {
            "broker": "paper",
            "name": "paper",
            "version": "1.0.0",
            "connected": True,
            "type": "simulated",
        }

    def close_sync(self) -> None:
        """Synchronous close method - kept for backward compatibility."""
        pass
    
    async def close(self) -> None:
        """Async close for CommonBrokerGateway protocol."""
        self.close_sync()
