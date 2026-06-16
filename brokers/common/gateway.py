"""MarketDataGateway v1.0 — frozen broker-agnostic contract.

This is the SINGLE interface that all broker adapters must implement.
No broker-specific fields are allowed in the contract.

Methods are grouped into:
  - Market Data (read-only): history, quote, ltp, depth, option_chain, future_chain, stream
  - Batch Market Data: ltp_batch, quote_batch, history_batch
  - Trading: place_order, cancel_order, get_orderbook, get_trade_book
  - Portfolio: positions, holdings, funds, trades
  - Instrument: search, load_instruments
  - Lifecycle: describe, capabilities, close

FROZEN: Do not add/remove/change method signatures after v1.0.
Any changes require a new major version.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core.domain import (
    Balance,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)

# ---------------------------------------------------------------------------
# Capability Matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrokerCapabilities:
    """Frozen capability matrix for a broker.

    Returned by gateway.capabilities(). Consumers use this to decide
    which features are available before calling methods.
    """

    # Market data capabilities
    expired_options: bool = False
    expired_futures: bool = False
    depth_20: bool = False
    depth_200: bool = False

    # Historical data limits
    max_intraday_days: int = 90
    max_daily_days: int = 365 * 10  # 10 years typical
    supported_timeframes: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "1D")

    # Batch capabilities
    parallel_history: bool = False
    max_batch_size: int = 1

    # Streaming capabilities
    websocket: bool = False
    polling_fallback: bool = True

    # Trading capabilities
    order_types: tuple[str, ...] = ("MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET")
    product_types: tuple[str, ...] = ("INTRADAY", "MARGIN")
    validities: tuple[str, ...] = ("DAY", "IOC")

    # Instrument capabilities
    load_instruments: bool = True
    search: bool = True

    # Rate limits
    rate_limit_per_second: int = 10
    rate_limit_per_minute: int = 200


# ---------------------------------------------------------------------------
# MarketDataGateway v1.0
# ---------------------------------------------------------------------------


class MarketDataGateway(ABC):
    """Frozen contract for broker-agnostic market data access.

    All broker adapters (Dhan, Upstox, Paper) must implement every method.
    No broker-specific fields are allowed in return types.

    Version: 1.0
    Frozen: 2026-06-14
    """

    # -----------------------------------------------------------------------
    # Market Data (read-only)
    # -----------------------------------------------------------------------

    @abstractmethod
    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Return OHLCV candles as a canonical DataFrame.

        Schema: timestamp, open, high, low, close, volume, oi, symbol, exchange, timeframe

        Parameters
        ----------
        symbol : str or list[str]
            Single symbol or list of symbols.
        exchange : str
            Exchange identifier (NSE, BSE, NFO, etc.).
        timeframe : str
            Candle interval: 1m, 5m, 15m, 30m, 1h, 1D.
        lookback_days : int
            Number of days to look back (ignored if from_date/to_date set).
        from_date : str or None
            Start date (YYYY-MM-DD). Overrides lookback_days.
        to_date : str or None
            End date (YYYY-MM-DD). Defaults to today.
        """
        ...

    @abstractmethod
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Return a canonical Quote with: symbol, ltp, open, high, low, close, volume, change, bid, ask, timestamp."""
        ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Return last traded price."""
        ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Return canonical MarketDepth with bids and asks."""
        ...

    @abstractmethod
    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        """Return option chain with strikes, CE/PE data.

        Returns dict with: underlying, exchange, expiry, strikes list[dict].
        """
        ...

    @abstractmethod
    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> dict:
        """Return futures chain with expiry dates and prices.

        Returns dict with: underlying, exchange, expiries list[str], contracts list[dict].
        """
        ...

    @abstractmethod
    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Start WebSocket streaming for a symbol.

        Parameters
        ----------
        mode : str
            LTP, QUOTE, or DEPTH.
        on_tick : callable or None
            Callback invoked with tick dict for each update.

        Returns
        -------
        Stream handle with .connect(), .disconnect(), .is_connected.
        """
        ...

    # -----------------------------------------------------------------------
    # Batch Market Data
    # -----------------------------------------------------------------------

    @abstractmethod
    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Return LTP for multiple symbols.

        Returns dict mapping symbol -> Decimal LTP.
        """
        ...

    @abstractmethod
    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, dict]:
        """Return quotes for multiple symbols.

        Returns dict mapping symbol -> quote dict.
        """
        ...

    @abstractmethod
    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Return historical data for multiple symbols.

        Returns concatenated DataFrame with 'symbol' column.
        """
        ...

    # -----------------------------------------------------------------------
    # Trading
    # -----------------------------------------------------------------------

    @abstractmethod
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
        """Place an order. Returns OrderResponse with success, order_id, message."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled."""
        ...

    @abstractmethod
    def get_orderbook(self) -> list[Order]:
        """Return all orders."""
        ...

    @abstractmethod
    def get_trade_book(self) -> list[Trade]:
        """Return all trades."""
        ...

    # -----------------------------------------------------------------------
    # Portfolio
    # -----------------------------------------------------------------------

    @abstractmethod
    def positions(self) -> list[Position]:
        """Return current positions."""
        ...

    @abstractmethod
    def holdings(self) -> list[Holding]:
        """Return holdings."""
        ...

    @abstractmethod
    def funds(self) -> Balance:
        """Return fund limits."""
        ...

    @abstractmethod
    def trades(self) -> list[Trade]:
        """Return trades (alias for get_trade_book)."""
        ...

    # -----------------------------------------------------------------------
    # Instrument
    # -----------------------------------------------------------------------

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """Search instruments by symbol name."""
        ...

    @abstractmethod
    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instrument master data."""
        ...

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities:
        """Return broker capability matrix."""
        ...

    @abstractmethod
    def describe(self) -> dict:
        """Return broker metadata: name, version, connected, etc."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close all connections and clean up resources."""
        ...
