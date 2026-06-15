"""Paper trading gateway — simulated broker for testing and development."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core.domain import (
    Balance,
    Holding,
    Order,
    OrderResponse,
    Trade,
)
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from brokers.common.oms.context import TradingContext
from brokers.common.oms.risk_manager import RiskConfig

from .paper_market_data import PaperMarketData
from .paper_orders import PaperOrders
from .paper_portfolio import PaperPortfolio


class PaperGateway(MarketDataGateway):
    """Unified paper-trading API implementing the frozen MarketDataGateway v1.0 contract.

    All market-data, order, and portfolio calls delegate to the
    corresponding adapter objects (``market_data``, ``orders``, ``portfolio``).

    Implements:
        - Market Data: history, quote, ltp, depth, option_chain, future_chain, stream
        - Batch: ltp_batch, quote_batch, history_batch
        - Trading: place_order, cancel_order, get_orderbook, get_trade_book
        - Portfolio: positions, holdings, funds, trades
        - Instrument: search, load_instruments
        - Lifecycle: describe, capabilities, close
    """

    def __init__(
        self,
        initial_capital: Decimal = Decimal("1000000"),
        trading_context: TradingContext | None = None,
    ) -> None:
        if trading_context is None:
            # Internal default context: paper trading is unrestricted unless the
            # caller supplies an explicit TradingContext with real risk limits.
            trading_context = TradingContext(
                capital_fn=lambda: initial_capital,
                risk_config=RiskConfig(
                    max_position_pct=Decimal("10000"),
                    max_gross_exposure_pct=Decimal("10000"),
                    max_daily_loss_pct=Decimal("10000"),
                ),
            )
        self._trading_context = trading_context
        self._market_data = PaperMarketData()
        self._orders = PaperOrders(
            self._market_data,
            {},
            order_manager=self._trading_context.order_manager,
            position_manager=self._trading_context.position_manager,
        )
        self._portfolio = PaperPortfolio(self._orders, initial_capital)

    @property
    def market_data(self) -> PaperMarketData:
        return self._market_data

    @property
    def orders(self) -> PaperOrders:
        return self._orders

    @property
    def trading_context(self) -> TradingContext:
        return self._trading_context

    @property
    def portfolio(self) -> PaperPortfolio:
        return self._portfolio

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
        import numpy as np
        from datetime import datetime, timedelta, timezone

        symbols = [symbol] if isinstance(symbol, str) else symbol
        n = lookback_days
        dates = [datetime.now(timezone.utc) - timedelta(days=n - i) for i in range(n)]

        rows = []
        for sym in symbols:
            np.random.seed(hash(sym) % 2**31)
            base_price = 500.0 + np.random.uniform(0, 4500)
            close = base_price + np.cumsum(np.random.randn(n) * base_price * 0.02)
            high = close + abs(np.random.randn(n)) * base_price * 0.01
            low = close - abs(np.random.randn(n)) * base_price * 0.01
            open_ = close + np.random.randn(n) * base_price * 0.005
            volume = np.random.randint(10000, 500000, n).astype(float)

            for i in range(n):
                rows.append({
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
                })

        return pd.DataFrame(rows)

    def quote(self, symbol: str, exchange: str = "NSE") -> dict:
        q = self._market_data.get_quote(symbol, exchange)
        return {
            "symbol": symbol,
            "ltp": float(q.ltp),
            "open": float(q.open),
            "high": float(q.high),
            "low": float(q.low),
            "close": float(q.close),
            "volume": q.volume,
            "change": float(q.change),
            "bid": float(q.bid) if q.bid else None,
            "ask": float(q.ask) if q.ask else None,
            "timestamp": q.timestamp.isoformat() if q.timestamp else None,
        }

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._market_data.get_ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> dict:
        d = self._market_data.get_depth(symbol, exchange)
        return {
            "symbol": symbol,
            "bids": [{"price": float(b.price), "quantity": b.quantity, "orders": b.orders} for b in d.bids],
            "asks": [{"price": float(a.price), "quantity": a.quantity, "orders": a.orders} for a in d.asks],
        }

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        import numpy as np
        base = float(self._market_data.get_ltp(underlying, "NSE"))
        strikes = [round(base + i * 50, 0) for i in range(-10, 11)]
        chain = []
        for strike in strikes:
            chain.append({
                "strike": strike,
                "expiry": expiry or "2026-07-30",
                "ce_ltp": round(max(0, base - strike + np.random.uniform(5, 50)), 2),
                "pe_ltp": round(max(0, strike - base + np.random.uniform(5, 50)), 2),
                "ce_oi": int(np.random.randint(10000, 100000)),
                "pe_oi": int(np.random.randint(10000, 100000)),
                "ce_volume": int(np.random.randint(1000, 50000)),
                "pe_volume": int(np.random.randint(1000, 50000)),
            })
        return {
            "underlying": underlying,
            "exchange": exchange,
            "expiry": expiry or "2026-07-30",
            "strikes": chain,
        }

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> dict:
        import numpy as np
        base = float(self._market_data.get_ltp(underlying, "NSE"))
        from datetime import datetime, timedelta
        expiries = [(datetime.now() + timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(1, 4)]
        contracts = []
        for exp in expiries:
            contracts.append({
                "expiry": exp,
                "ltp": round(base * (1 + np.random.uniform(-0.02, 0.03)), 2),
                "volume": int(np.random.randint(10000, 500000)),
                "oi": int(np.random.randint(50000, 1000000)),
                "change": round(np.random.uniform(-2, 2), 2),
            })
        return {
            "underlying": underlying,
            "exchange": exchange,
            "expiries": expiries,
            "contracts": contracts,
        }

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        class _PaperStream:
            def connect(self): pass
            def disconnect(self): pass
            @property
            def is_connected(self): return False
        return _PaperStream()

    # =======================================================================
    # Batch Market Data
    # =======================================================================

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return {sym: self._market_data.get_ltp(sym, exchange) for sym in symbols}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, dict]:
        return {sym: self.quote(sym, exchange) for sym in symbols}

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        return self.history(symbols, exchange, timeframe, lookback_days)

    # =======================================================================
    # Trading
    # =======================================================================

    def place_order(self, *args, **kwargs) -> OrderResponse:
        order = self._orders.place_order(*args, **kwargs)
        return OrderResponse(
            success=True,
            order_id=order.order_id,
            message="Order filled (paper)",
            status=order.status,
        )

    def cancel_order(self, order_id: str) -> bool:
        return self._orders.cancel_order(order_id)

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
        return BrokerCapabilities(
            expired_options=True,
            expired_futures=False,
            depth_20=True,
            depth_200=False,
            max_intraday_days=365 * 10,
            max_daily_days=365 * 10,
            supported_timeframes=("1m", "5m", "15m", "30m", "1h", "1D"),
            parallel_history=True,
            max_batch_size=100,
            websocket=False,
            polling_fallback=True,
            order_types=("MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"),
            product_types=("INTRADAY", "MARGIN", "CNC"),
            validities=("DAY", "IOC"),
            load_instruments=True,
            search=True,
            rate_limit_per_second=100,
            rate_limit_per_minute=10000,
        )

    def describe(self) -> dict:
        return {
            "name": "paper",
            "version": "1.0.0",
            "connected": True,
            "type": "simulated",
        }

    def close(self) -> None:
        pass
