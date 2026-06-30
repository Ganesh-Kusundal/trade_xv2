"""IntelligentMarketDataGateway — smart routing gateway with intelligent infrastructure.

This gateway wraps BrokerInfrastructure and provides the same MarketDataGateway
interface but uses intelligent routing internally:

- BrokerRouter: Automatic broker selection based on policy and health
- QuotaScheduler: Multi-broker quota coordination and rate limit management
- HistoricalDataCoordinator: Parallel multi-broker historical data fetching

Two modes:
- smart=True (default): Uses intelligent infrastructure for optimal performance
- smart=False: Direct broker calls (legacy behavior, single broker)

Usage::

    # Smart mode (recommended)
    gw = IntelligentMarketDataGateway(infra, smart=True)
    result = gw.ltp("NIFTY", "NSE")  # Uses router + quota scheduler

    # Simple mode (backward compatible)
    gw = IntelligentMarketDataGateway(infra, smart=False)
    result = gw.ltp("NIFTY", "NSE")  # Direct call to primary broker
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.gateway import MarketDataGateway
from brokers.common.historical_coordinator import HistoricalQuery
from brokers.common.infrastructure import BrokerInfrastructure
from brokers.common.models import OperationKind, RoutingRequest
from brokers.common.quota_decorator import routed
from brokers.common.quota_scheduler import PriorityClass
from domain import (
    Balance,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from domain.constants import DEFAULT_DERIVATIVES_EXCHANGE, DEFAULT_EXCHANGE
from domain.historical import InstrumentRef

logger = logging.getLogger(__name__)


class IntelligentMarketDataGateway(MarketDataGateway):
    """Intelligent gateway with smart routing and quota management.

    Parameters
    ----------
    infrastructure : BrokerInfrastructure
        The broker infrastructure containing router, quota scheduler, etc.
    smart : bool, default=True
        Enable intelligent routing. When True, uses BrokerRouter for broker
        selection and QuotaScheduler for quota management. When False, delegates
        directly to primary_broker.
    primary_broker : str, default="dhan"
        The broker to use when smart=False or as the primary broker in smart mode.
    """

    def __init__(
        self,
        infrastructure: BrokerInfrastructure,
        *,
        smart: bool = True,
        primary_broker: str = "dhan",
    ) -> None:
        self._infra = infrastructure
        self._smart = smart
        self._primary = primary_broker

    @property
    def smart_mode(self) -> bool:
        """Return whether smart routing is enabled."""
        return self._smart

    @property
    def primary_broker(self) -> str:
        """Return the primary broker ID."""
        return self._primary

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _get_gateway(self, operation: OperationKind) -> MarketDataGateway:
        """Get the appropriate gateway based on smart mode.

        In smart mode, uses BrokerRouter to select the best broker.
        In simple mode, returns the primary broker gateway.
        """
        if not self._smart:
            return self._infra.gateway_for(self._primary)

        # Smart mode: Use router
        try:
            import uuid
            trace_id = str(uuid.uuid4())[:8]
            request = RoutingRequest(operation=operation, trace_id=trace_id)
            decision = self._infra.router.route(request)
            return self._infra.registry.get_gateway(decision.primary_broker)
        except Exception as exc:
            logger.warning(
                "routing_failed_falling_back_to_primary",
                extra={"operation": operation.value, "error": str(exc), "fallback": self._primary},
            )
            return self._infra.gateway_for(self._primary)

    def _acquire_quota(self, broker_id: str, endpoint_class: str) -> Any:
        """Acquire a quota token for the operation.

        Returns the token (must be released after use).
        """
        if not self._smart:
            return None

        try:
            return self._infra.quota.acquire(broker_id, endpoint_class, PriorityClass.PORTFOLIO_READ)
        except Exception as exc:
            logger.warning(
                "quota_acquire_failed",
                extra={"broker": broker_id, "endpoint": endpoint_class, "error": str(exc)},
            )
            return None

    def _release_quota(self, token: Any) -> None:
        """Release a quota token after use."""
        if token is not None and self._smart:
            try:
                self._infra.quota.release(token)
            except Exception as exc:
                logger.warning("quota_release_failed", extra={"error": str(exc)})

    # -----------------------------------------------------------------------
    # Market Data (read-only)
    # -----------------------------------------------------------------------

    @routed(OperationKind.GET_QUOTE, "quotes")
    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        """Return last traded price with intelligent routing."""
        return self._gateway.ltp(symbol, exchange)

    @routed(OperationKind.GET_QUOTE, "quotes")
    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
        """Return quote with intelligent routing."""
        return self._gateway.quote(symbol, exchange)

    @routed(OperationKind.GET_DEPTH, "quotes")
    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
        """Return market depth with intelligent routing."""
        return self._gateway.depth(symbol, exchange)

    def history(
        self,
        symbol: str | list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Return historical data with intelligent multi-broker fetching.

        In smart mode, uses HistoricalDataCoordinator for parallel fetching
        across multiple brokers. In simple mode, delegates to primary broker.
        """
        # Handle list of symbols
        if isinstance(symbol, list):
            return self.history_batch(symbol, exchange, timeframe, lookback_days)

        # Parse dates
        if from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d").date()
        else:
            start = date.today() - pd.Timedelta(days=lookback_days)

        if to_date:
            end = datetime.strptime(to_date, "%Y-%m-%d").date()
        else:
            end = date.today()

        if self._smart:
            # Use HistoricalDataCoordinator for parallel multi-broker fetching
            try:
                query = HistoricalQuery(
                    instrument=InstrumentRef(symbol, exchange),
                    timeframe=timeframe,
                    from_date=start,
                    to_date=end,
                )
                series, _ledger = self._infra.historical.fetch(query)
                return series.to_dataframe()
            except Exception as exc:
                logger.warning(
                    "historical_coordinator_failed_falling_back",
                    extra={"symbol": symbol, "error": str(exc)},
                )

        # Simple mode or fallback
        gateway = self._get_gateway(OperationKind.GET_HISTORICAL_BARS)
        broker_id = getattr(gateway, "broker_id", self._primary)
        token = self._acquire_quota(broker_id, "historical")
        try:
            return gateway.history(symbol, exchange, timeframe, lookback_days, from_date, to_date)
        finally:
            self._release_quota(token)

    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        """Return option chain with intelligent routing."""
        gateway = self._get_gateway(OperationKind.FETCH_OPTION_CHAIN)
        broker_id = getattr(gateway, "broker_id", self._primary)
        token = self._acquire_quota(broker_id, "option_chain")
        try:
            return gateway.option_chain(underlying, exchange, expiry)
        finally:
            self._release_quota(token)

    def future_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
    ) -> FutureChain:
        """Return future chain with intelligent routing."""
        gateway = self._get_gateway(OperationKind.GET_QUOTE)  # Future chain uses quote operation
        broker_id = getattr(gateway, "broker_id", self._primary)
        token = self._acquire_quota(broker_id, "quotes")
        try:
            return gateway.future_chain(underlying, exchange)
        finally:
            self._release_quota(token)

    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Start WebSocket streaming (delegates to primary broker)."""
        # Streaming is broker-specific, so always use primary broker
        return self._infra.gateway_for(self._primary).stream(symbol, exchange, mode, on_tick)

    # -----------------------------------------------------------------------
    # Batch Market Data
    # -----------------------------------------------------------------------

    def ltp_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Decimal]:
        """Return LTP for multiple symbols with intelligent routing.

        In smart mode, splits symbols across brokers based on quota headroom.
        In simple mode, delegates to primary broker.
        """
        if not self._smart or len(symbols) < 5:
            # Small batches or simple mode: use primary broker
            gateway = self._get_gateway(OperationKind.GET_QUOTE)  # Batch uses quote operation
            broker_id = getattr(gateway, "broker_id", self._primary)
            token = self._acquire_quota(broker_id, "quotes")
            try:
                return gateway.ltp_batch(symbols, exchange)
            finally:
                self._release_quota(token)

        # Smart mode: Split across brokers
        allocations = self._allocate_symbols_to_brokers(symbols)
        results = {}
        for broker_id, broker_symbols in allocations.items():
            gateway = self._infra.registry.get_gateway(broker_id)
            token = self._acquire_quota(broker_id, "quotes")
            try:
                batch_result = gateway.ltp_batch(broker_symbols, exchange)
                results.update(batch_result)
            finally:
                self._release_quota(token)
        return results

    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Quote]:
        """Return quotes for multiple symbols with intelligent routing."""
        if not self._smart or len(symbols) < 5:
            gateway = self._get_gateway(OperationKind.GET_QUOTE)
            broker_id = getattr(gateway, "broker_id", self._primary)
            token = self._acquire_quota(broker_id, "quotes")
            try:
                return gateway.quote_batch(symbols, exchange)
            finally:
                self._release_quota(token)

        # Smart mode: Split across brokers
        allocations = self._allocate_symbols_to_brokers(symbols)
        results = {}
        for broker_id, broker_symbols in allocations.items():
            gateway = self._infra.registry.get_gateway(broker_id)
            token = self._acquire_quota(broker_id, "quotes")
            try:
                batch_result = gateway.quote_batch(broker_symbols, exchange)
                results.update(batch_result)
            finally:
                self._release_quota(token)
        return results

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Return historical data for multiple symbols with intelligent routing."""
        if not self._smart:
            gateway = self._get_gateway(OperationKind.GET_HISTORICAL_BARS)
            broker_id = getattr(gateway, "broker_id", self._primary)
            token = self._acquire_quota(broker_id, "historical")
            try:
                return gateway.history_batch(symbols, exchange, timeframe, lookback_days)
            finally:
                self._release_quota(token)

        # Smart mode: Fetch in parallel
        frames = []
        for symbol in symbols:
            try:
                df = self.history(symbol, exchange, timeframe, lookback_days)
                df["symbol"] = symbol
                frames.append(df)
            except Exception as exc:
                logger.warning(
                    "history_batch_symbol_failed",
                    extra={"symbol": symbol, "error": str(exc)},
                )

        if not frames:
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)

    # -----------------------------------------------------------------------
    # Trading
    # -----------------------------------------------------------------------

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
        transport_only: bool = False,
    ) -> OrderResponse:
        """Place an order (always uses primary broker for execution)."""
        # Order execution is critical — always use primary broker
        gateway = self._infra.gateway_for(self._primary)
        return gateway.place_order(
            symbol,
            exchange,
            side,
            quantity,
            price,
            order_type,
            product_type,
            validity,
            trigger_price,
            correlation_id,
            transport_only,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order (always uses primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.cancel_order(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an order (always uses primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.modify_order(order_id, **changes)

    def get_orderbook(self) -> list[Order]:
        """Return all orders (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        """Return all trades (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.get_trade_book()

    # -----------------------------------------------------------------------
    # Portfolio
    # -----------------------------------------------------------------------

    def positions(self) -> list[Position]:
        """Return current positions (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.positions()

    def holdings(self) -> list[Holding]:
        """Return holdings (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.holdings()

    def funds(self) -> Balance:
        """Return fund limits (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.funds()

    def trades(self) -> list[Trade]:
        """Return trades (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.trades()

    # -----------------------------------------------------------------------
    # Instrument
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list[dict]:
        """Search instruments (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.search(query)

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instrument master data (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.load_instruments(source, use_cache)

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def capabilities(self) -> Any:
        """Return broker capability matrix (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.capabilities()

    def describe(self) -> dict:
        """Return broker metadata (from primary broker)."""
        gateway = self._infra.gateway_for(self._primary)
        return gateway.describe()

    def close(self) -> None:
        """Close all connections and clean up resources."""
        # Close all gateways in infrastructure
        for broker_id in self._infra.registry.list_brokers():
            try:
                gateway = self._infra.registry.get_gateway(broker_id)
                gateway.close()
            except Exception as exc:
                logger.warning(
                    "gateway_close_failed",
                    extra={"broker": broker_id, "error": str(exc)},
                )

    # -----------------------------------------------------------------------
    # Intelligent Helpers
    # -----------------------------------------------------------------------

    def _allocate_symbols_to_brokers(self, symbols: list[str]) -> dict[str, list[str]]:
        """Allocate symbols across brokers based on quota headroom.

        Returns a mapping of broker_id -> list[symbols].
        """
        if not self._smart:
            return {self._primary: symbols}

        # Get all available brokers
        available_brokers = list(self._infra.registry.list_brokers())
        if not available_brokers:
            return {self._primary: symbols}

        # Simple round-robin allocation based on quota headroom
        allocations: dict[str, list[str]] = {bid: [] for bid in available_brokers}
        for i, symbol in enumerate(symbols):
            broker_id = available_brokers[i % len(available_brokers)]
            allocations[broker_id].append(symbol)

        # Remove empty allocations
        return {bid: syms for bid, syms in allocations.items() if syms}
