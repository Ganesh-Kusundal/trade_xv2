"""Focused gateway interfaces (REF-18 ISP split)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import pandas as pd

from domain import FutureChain, MarketDepth, OptionChain, Order, OrderResponse, Quote
from domain.requests import OrderRequest


class MarketDataProvider(ABC):
    @abstractmethod
    def history(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "1D",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame: ...

    @abstractmethod
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote: ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal: ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth: ...


class DerivativesProvider(ABC):
    @abstractmethod
    def option_chain(
        self, underlying: str, exchange: str = "NFO", expiry: str | None = None
    ) -> OptionChain: ...

    @abstractmethod
    def future_chain(
        self, underlying: str, exchange: str = "NFO", expiry: str | None = None
    ) -> FutureChain: ...


class BatchMarketDataProvider(ABC):
    @abstractmethod
    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]: ...

    @abstractmethod
    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Any]: ...

    @abstractmethod
    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, pd.DataFrame]: ...


class TradingExecutor(ABC):
    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse: ...

    @abstractmethod
    def get_orderbook(self) -> list[Order]: ...

    @abstractmethod
    def get_trade_book(self) -> list[Any]: ...


class PortfolioReader(ABC):
    @abstractmethod
    def positions(self) -> list[Any]: ...

    @abstractmethod
    def holdings(self) -> list[Any]: ...

    @abstractmethod
    def funds(self) -> Any: ...

    @abstractmethod
    def trades(self) -> list[Any]: ...


class InstrumentProvider(ABC):
    @abstractmethod
    def search(self, query: str, exchange: str | None = None) -> list[Any]: ...

    @abstractmethod
    def load_instruments(self, exchange: str = "NSE") -> int: ...


class StreamProvider(ABC):
    @abstractmethod
    def stream(self, symbols: list[str], exchange: str = "NSE", mode: str = "LTP") -> Any: ...


class LifecycleAware(ABC):
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
