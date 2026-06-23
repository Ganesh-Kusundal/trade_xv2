"""Focused gateway interfaces (REF-18 ISP split, REF-028 aligned with MarketDataGateway).

These narrow interfaces decompose the monolithic ``MarketDataGateway``
by concern. Signatures are aligned with the concrete gateway implementations
so that ``MarketDataGateway`` can inherit from all of them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import pandas as pd

from domain import FutureChain, MarketDepth, OptionChain, Order, OrderResponse, Quote


class MarketDataProvider(ABC):
    """Narrow interface for OHLCV, quote, LTP, and depth."""

    @abstractmethod
    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame: ...

    @abstractmethod
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote: ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal: ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth: ...


class DerivativesProvider(ABC):
    """Narrow interface for option and futures chain data."""

    @abstractmethod
    def option_chain(
        self, underlying: str, exchange: str = "NFO", expiry: str | None = None
    ) -> OptionChain: ...

    @abstractmethod
    def future_chain(
        self, underlying: str, exchange: str = "NFO"
    ) -> FutureChain: ...


class BatchMarketDataProvider(ABC):
    """Narrow interface for batched LTP, quote, and history."""

    @abstractmethod
    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]: ...

    @abstractmethod
    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, dict]: ...

    @abstractmethod
    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame: ...


class TradingExecutor(ABC):
    """Narrow interface for order placement, cancellation, and trade/order book.

    The ``place_order`` signature matches the concrete gateway implementations.
    For typed order requests, use :class:`~domain.requests.OrderRequest`
    as an alternative construction pattern.
    """

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
    ) -> OrderResponse: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse: ...

    @abstractmethod
    def get_orderbook(self) -> list[Order]: ...

    @abstractmethod
    def get_trade_book(self) -> list[Any]: ...


class PortfolioReader(ABC):
    """Narrow interface for positions, holdings, funds, and trades."""

    @abstractmethod
    def positions(self) -> list[Any]: ...

    @abstractmethod
    def holdings(self) -> list[Any]: ...

    @abstractmethod
    def funds(self) -> Any: ...

    @abstractmethod
    def trades(self) -> list[Any]: ...


class InstrumentProvider(ABC):
    """Narrow interface for instrument search and loading."""

    @abstractmethod
    def search(self, query: str) -> list[dict]: ...

    @abstractmethod
    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None: ...


class StreamProvider(ABC):
    """Narrow interface for real-time streaming."""

    @abstractmethod
    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any: ...


class LifecycleAware(ABC):
    """Narrow interface for broker lifecycle (describe, capabilities, close)."""

    @abstractmethod
    def describe(self) -> dict[str, Any]: ...

    @abstractmethod
    def capabilities(self) -> Any: ...

    @abstractmethod
    def close(self) -> None: ...


__all__ = [
    "BatchMarketDataProvider",
    "DerivativesProvider",
    "InstrumentProvider",
    "LifecycleAware",
    "MarketDataProvider",
    "PortfolioReader",
    "StreamProvider",
    "TradingExecutor",
]
