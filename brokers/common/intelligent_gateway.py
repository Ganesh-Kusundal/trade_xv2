"""Intelligent Gateway — combines Dhan and Upstox for optimal performance.

Routes requests to the fastest broker for each operation type.
Supports parallel data fetching for batch operations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.data_contracts import Quote, MarketDepth, FundLimits


class IntelligentGateway:
    """Combines Dhan and Upstox for optimal performance.

    Routing strategy:
    - LTP/Quote: Upstox (faster batch operations)
    - History: Dhan (better intraday support)
    - Option Chain: Dhan (more complete)
    - Future Chain: Dhan (Upstox doesn't support)
    - Depth: Dhan (Upstox endpoint deprecated)
    - Positions/Holdings/Funds: Use first available
    """

    def __init__(self, dhan_gateway=None, upstox_gateway=None):
        self._dhan = dhan_gateway
        self._upstox = upstox_gateway

    @property
    def dhan(self):
        return self._dhan

    @property
    def upstox(self):
        return self._upstox

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Route to Upstox for faster LTP."""
        if self._upstox:
            try:
                return self._upstox.ltp(symbol, exchange)
            except Exception:
                pass
        if self._dhan:
            return self._dhan.ltp(symbol, exchange)
        raise RuntimeError("No broker available")

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get LTP for multiple symbols using parallel fetching."""
        if self._upstox:
            try:
                return self._upstox.ltp_batch(symbols, exchange)
            except Exception:
                pass
        if self._dhan:
            return self._dhan.ltp_batch(symbols, exchange)
        raise RuntimeError("No broker available")

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Route to Upstox for faster quotes."""
        if self._upstox:
            try:
                return self._upstox.quote(symbol, exchange)
            except Exception:
                pass
        if self._dhan:
            return self._dhan.quote(symbol, exchange)
        raise RuntimeError("No broker available")

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Get quotes for multiple symbols using parallel fetching."""
        if self._upstox:
            try:
                return self._upstox.quote_batch(symbols, exchange)
            except Exception:
                pass
        if self._dhan:
            return self._dhan.quote_batch(symbols, exchange)
        raise RuntimeError("No broker available")

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1m",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Route to Dhan for better historical data support."""
        if self._dhan:
            try:
                return self._dhan.history(symbol, exchange, timeframe, lookback_days, from_date, to_date)
            except Exception:
                pass
        if self._upstox:
            return self._upstox.history(symbol, exchange, timeframe, lookback_days, from_date, to_date)
        raise RuntimeError("No broker available")

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Fetch history for multiple symbols using parallel fetching."""
        if self._dhan:
            try:
                return self._dhan.history_batch(symbols, exchange, timeframe, lookback_days)
            except Exception:
                pass
        if self._upstox:
            return self._upstox.history_batch(symbols, exchange, timeframe, lookback_days)
        raise RuntimeError("No broker available")

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Route to Dhan (Upstox endpoint deprecated)."""
        if self._dhan:
            try:
                return self._dhan.depth(symbol, exchange)
            except Exception:
                pass
        if self._upstox:
            return self._upstox.depth(symbol, exchange)
        raise RuntimeError("No broker available")

    def option_chain(
        self,
        underlying: str,
        exchange: str = "INDEX",
        expiry: str | None = None,
    ) -> dict:
        """Route to Dhan for better option chain support."""
        if self._dhan:
            try:
                return self._dhan.option_chain(underlying, exchange, expiry)
            except Exception:
                pass
        if self._upstox:
            return self._upstox.option_chain(underlying, exchange, expiry)
        raise RuntimeError("No broker available")

    def future_chain(
        self,
        underlying: str,
        exchange: str = "INDEX",
    ) -> dict:
        """Route to Dhan (Upstox doesn't support)."""
        if self._dhan:
            try:
                return self._dhan.future_chain(underlying, exchange)
            except Exception:
                pass
        return {"underlying": underlying, "exchange": exchange, "expiries": [], "contracts": []}

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Route to Dhan for streaming."""
        if self._dhan:
            try:
                return self._dhan.stream(symbol, exchange, mode, on_tick)
            except Exception:
                pass
        if self._upstox:
            return self._upstox.stream(symbol, exchange, mode, on_tick)
        raise RuntimeError("No broker available")

    def positions(self) -> list[Any]:
        """Get positions from first available broker."""
        if self._dhan:
            try:
                return self._dhan.positions()
            except Exception:
                pass
        if self._upstox:
            return self._upstox.positions()
        return []

    def holdings(self) -> list[Any]:
        """Get holdings from first available broker."""
        if self._dhan:
            try:
                return self._dhan.holdings()
            except Exception:
                pass
        if self._upstox:
            return self._upstox.holdings()
        return []

    def funds(self) -> FundLimits:
        """Get funds from first available broker."""
        if self._dhan:
            try:
                return self._dhan.funds()
            except Exception:
                pass
        if self._upstox:
            return self._upstox.funds()
        return FundLimits()

    def trades(self) -> list[Any]:
        """Get trades from first available broker."""
        if self._dhan:
            try:
                return self._dhan.trades()
            except Exception:
                pass
        if self._upstox:
            return self._upstox.trades()
        return []

    def describe(self) -> dict:
        """Return combined broker metadata."""
        brokers = []
        if self._dhan:
            brokers.append("Dhan")
        if self._upstox:
            brokers.append("Upstox")
        return {
            "brokers": brokers,
            "routing": {
                "ltp": "Upstox (faster)",
                "quote": "Upstox (faster)",
                "history": "Dhan (better support)",
                "depth": "Dhan (Upstox deprecated)",
                "option_chain": "Dhan (more complete)",
                "future_chain": "Dhan (Upstox doesn't support)",
                "stream": "Dhan",
            }
        }

    def search(self, query: str) -> list[dict]:
        """Search instruments from first available broker."""
        if self._dhan:
            try:
                return self._dhan.search(query)
            except Exception:
                pass
        if self._upstox:
            return self._upstox.search(query)
        return []
