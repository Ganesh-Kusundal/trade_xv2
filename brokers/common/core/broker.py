"""Abstract Broker interface — the canonical contract every adapter must implement.

All broker adapters MUST satisfy this interface.  The rest of TradeXV2
only depends on this ABC, never on Dhan/Upstox/Zerodha internals.

Usage::

    from brokers.common.core.broker import Broker

    class MyBroker(Broker):
        ...

    broker = MyBroker()
    df = broker.get_historical_data("RELIANCE", "NSE", from_date, to_date)
    # df is always a pd.DataFrame with HistoricalSchema columns
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from pandas import DataFrame

from brokers.common.core.domain import (
    FundLimits,
    Holding,
    Order,
    OrderResponse,
    Position,
    Side,
    Trade,
)


class Broker(ABC):
    """Abstract broker interface — every adapter must implement this.

    Market data methods return DataFrames (canonical schemas).
    Trading methods return domain objects (dataclasses).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker name (e.g. 'dhan', 'paper', 'upstox')."""
        ...

    @property
    @abstractmethod
    def broker_id(self) -> str:
        """Unique broker identifier."""
        ...

    # ── Connection lifecycle ───────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """Tear down connection."""
        ...

    def is_connected(self) -> bool:
        """Whether the broker is currently connected."""
        return False

    # ── Market data (returns DataFrames) ──────────────────────────────

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        exchange: str,
        from_date: date,
        to_date: date,
        timeframe: str = "1d",
    ) -> DataFrame:
        """Return historical OHLCV candles as a canonical DataFrame.

        Schema: HistoricalSchema — timestamp, open, high, low, close,
        volume, oi, symbol, exchange, timeframe.
        """
        ...

    @abstractmethod
    def get_quote(
        self,
        symbol: str,
        exchange: str,
    ) -> DataFrame:
        """Return real-time quote as a canonical DataFrame.

        Schema: QuoteSchema — symbol, exchange, ltp, bid, ask,
        volume, oi, timestamp.
        """
        ...

    @abstractmethod
    def get_option_chain(
        self,
        underlying: str,
        exchange: str,
        expiry: str,
    ) -> DataFrame:
        """Return option chain as a canonical DataFrame.

        Schema: OptionChainSchema — underlying, expiry,
        strike, option_type, ltp, bid, ask, volume, oi, iv,
        delta, gamma, theta, vega, rho, timestamp.
        """
        ...

    @abstractmethod
    def get_market_depth(
        self,
        symbol: str,
        exchange: str,
    ) -> DataFrame:
        """Return L2 market depth as a canonical DataFrame.

        Schema: MarketDepthSchema — symbol, timestamp,
        bid_price_1..20, bid_qty_1..20, ask_price_1..20, ask_qty_1..20.
        """
        ...

    # ── Trading (returns domain objects) ───────────────────────────────

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        """Place an order and return a canonical OrderResponse."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Fetch a single order by ID."""
        ...

    @abstractmethod
    def get_orders(self) -> list[Order]:
        """Fetch all orders for the day."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order. Returns True on success."""
        ...

    # ── Portfolio (returns domain objects) ─────────────────────────────

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return current positions."""
        ...

    @abstractmethod
    def get_holdings(self) -> list[Holding]:
        """Return holdings in the demat account."""
        ...

    @abstractmethod
    def get_fund_limits(self) -> FundLimits:
        """Return account fund limits."""
        ...

    # ── Trades ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_trades(self) -> list[Trade]:
        """Return the trade book for the day."""
        ...
