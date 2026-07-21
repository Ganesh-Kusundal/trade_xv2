"""BrokerMarketDataPort — read-only market data operations for broker adapters.

Narrow ABC that captures the data-access surface of a broker. Callers that
only need market data (scanners, analytics, backtest engines) should depend
on this port instead of the full :class:`BrokerAdapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

    from domain.entities import MarketDepth, OptionChain, Quote
    from domain.entities.options import FutureChain
    from domain.capabilities.broker_capabilities import BrokerCapabilities, CapabilityDescriptor


class BrokerMarketDataPort(ABC):
    """Read-only market data operations — the data-access surface of a broker.

    This is a focused subset of :class:`BrokerAdapter`. Callers that only need
    market data (scanners, analytics, backtest engines) should depend on this
    port instead of the full broker interface.
    """

    broker_id: str = ""
    is_connected: bool = False

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate against the broker; return True on success."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Tear down the connection and release resources."""
        ...

    @abstractmethod
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get latest quote for a symbol."""
        ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Get last traded price for a symbol."""
        ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get market depth (order book) for a symbol."""
        ...

    @abstractmethod
    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Any:
        """Get historical OHLCV data."""
        ...

    @abstractmethod
    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get option chain for an underlying."""
        ...

    @abstractmethod
    def future_chain(self, underlying: str, exchange: str = "NFO") -> FutureChain:
        """Get futures chain for an underlying."""
        ...

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """Search for instruments by query string."""
        ...

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities:
        """Return the capability matrix for this broker."""
        ...

    @abstractmethod
    def list_capabilities(self) -> CapabilityDescriptor:
        """Return capability descriptor (registry/router compatible)."""
        ...

    @abstractmethod
    def describe(self) -> dict:
        """Return broker metadata dict."""
        ...

    @abstractmethod
    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instruments into the broker-internal resolver."""
        ...
