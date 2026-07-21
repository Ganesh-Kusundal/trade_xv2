"""Paper trading gateway — simulated broker for testing and development."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pandas as pd

from domain.capabilities.broker_capabilities import BrokerCapabilities
from brokers.common.wire_base import BaseWireAdapter
from domain.entities import (
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
from domain.enums import OrderStatus
from domain.constants import DEFAULT_EXCHANGE
from domain.constants.defaults import PAPER_INITIAL_CAPITAL
from domain.ports.broker_adapter import BrokerAdapter
from domain.orders.requests import OrderRequest

from .paper_market_data import PaperMarketData
from .paper_orders import PaperOrders
from .paper_portfolio import PaperPortfolio


class PaperGateway(BaseWireAdapter, BrokerAdapter):
    """Synthetic market-data adapter for tests — NOT authoritative for OMS state.

    ponytail: ADR-0012 — PaperGateway supplies quotes/history only. Paper orders,
    capital, positions, and risk authority live in the OMS + PaperFillSource path.
    Do not use ``portfolio``/``funds()`` output as production risk capital.
    """

    broker_id = "paper"

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

    def place_order(self, request: OrderRequest) -> OrderResponse:
        from brokers.common.util import enum_value

        order = self._orders.place_order(
            symbol=request.symbol,
            exchange=enum_value(request.exchange),
            side=enum_value(request.transaction_type),
            quantity=request.quantity,
            price=request.price,
            order_type=enum_value(request.order_type),
            product_type=enum_value(request.product_type),
            validity=enum_value(request.validity),
            trigger_price=request.trigger_price or Decimal("0"),
            correlation_id=request.correlation_id,
        )
        return OrderResponse(
            success=order.status not in (OrderStatus.REJECTED, OrderStatus.EXPIRED),
            order_id=order.order_id,
            message="Order filled (paper)" if order.status == OrderStatus.FILLED else f"Order {order.status.value.lower()} (paper)",
            status=order.status,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        # PaperOrders.cancel_order returns True if order was found and cancelled, False otherwise
        success = self._orders.cancel_order(order_id)
        cancelled_order = self._orders.get_order(order_id)

        if success and cancelled_order:
            return OrderResponse(
                success=True,
                order_id=order_id,
                message="Order cancelled (paper)",
                status=OrderStatus.CANCELLED,
            )
        elif cancelled_order and cancelled_order.status == OrderStatus.FILLED:
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

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        # Map values if they are enums
        mapped_changes = {}
        for k, v in changes.items():
            if k == "order_type" or k == "validity" or k == "product_type":
                mapped_changes[k] = v.value if hasattr(v, "value") else str(v)
            else:
                mapped_changes[k] = v

        try:
            order = self._orders.modify_order(order_id, **mapped_changes)
        except ValueError as exc:
            return OrderResponse.fail(message=str(exc), status=OrderStatus.REJECTED)
        return OrderResponse(
            success=order is not None,
            order_id=order_id,
            message="Order modified (paper)" if order else "Order not found",
            status=order.status if order else None,
        )

    # =======================================================================
    # Market Data (read-only)
    # =======================================================================

    def history(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        import hashlib
        from datetime import timedelta

        import numpy as np

        from domain.ports.time_service import get_current_clock

        symbols = [symbol]
        n = lookback_days
        dates = [get_current_clock().now() - timedelta(days=n - i) for i in range(n)]

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

    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
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

    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        return self._market_data.get_ltp(symbol, exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Decimal]:
        return {sym: self.ltp(sym, exchange) for sym in symbols}

    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
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
        """Synthetic chain with spot, OI, IV, and rough greeks (DV-013 paper path)."""
        from brokers.providers.paper.synthetic_options import generate_option_chain

        base = float(self._market_data.get_ltp(underlying, "NSE"))
        chain_dict = generate_option_chain(underlying, exchange, base, expiry)
        return OptionChain.from_dict(chain_dict)

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        from brokers.providers.paper.synthetic_options import generate_future_chain

        base = float(self._market_data.get_ltp(underlying, "NSE"))
        contracts = generate_future_chain(underlying, base)
        from domain.ports.time_service import get_current_clock
        from datetime import timedelta

        expiries = [
            (get_current_clock().now() + timedelta(days=30 * i)).strftime("%Y-%m-%d")
            for i in range(1, 4)
        ]
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
        exchange: str = DEFAULT_EXCHANGE,
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

    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        *,
        levels: int = 5,
        on_depth: Callable[[MarketDepth], None] | None = None,
        depth_type: str | None = None,  # deprecated — use levels instead
    ) -> Any:
        # ponytail: depth_type accepted for backward compat but ignored by paper simulator.
        class _PaperStream:
            def connect(self):
                pass

            def disconnect(self):
                pass

            @property
            def is_connected(self):
                return False

        return _PaperStream()

    def unstream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        on_tick: Any | None = None,
    ) -> None:
        pass  # Paper streams are noop

    def stream_order(self, on_order: Any | None = None) -> Any:
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

    def _seed_orders(self, orders: list[Order]) -> None:
        self._orders._orders = orders

    def _seed_trades(self, trades: list[Trade]) -> None:
        self._orders._trades = trades

    def _seed_positions(self, positions: dict[str, Position]) -> None:
        self._orders._positions = positions

    def _seed_holdings(self, holdings: list[Holding]) -> None:
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

    def list_capabilities(self):
        """BrokerAdapter-compatible capability descriptor (registry/router)."""
        from domain.capabilities.broker_capabilities import CapabilityDescriptor

        return CapabilityDescriptor.build(self.capabilities(), frozenset())

    def authenticate(self) -> bool:
        """Paper gateway is always authenticated."""
        return True

    def capabilities(self) -> BrokerCapabilities:
        from brokers.providers.paper.capabilities import paper_capabilities

        return paper_capabilities()

    def describe(self) -> dict:
        return {
            "broker": "paper",
            "name": "paper",
            "version": "1.0.0",
            "connected": True,
            "type": "simulated",
        }

    def close(self) -> None:
        """Close resources (noop for simulated gateway)."""
        pass
