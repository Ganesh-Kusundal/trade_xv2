"""Intelligent Gateway — combines Dhan and Upstox for optimal performance.

Routes requests to the fastest broker for each operation type.
Supports parallel data fetching for batch operations.

Observability contract
----------------------
Every silent ``except Exception: pass`` from the previous version has been
replaced with a call to :meth:`IntelligentGateway._log_fallback`. Each
fallback:

1. Logs at WARNING level with the operation, the failing broker, and the
   exception type / message.
2. Increments the ``intelligent_gateway_fallback`` counter on the
   attached :class:`EventMetrics` instance (keyed by operation, broker,
   and exception class name) so an SRE can alert on systemic broker
   outages.
3. Returns the fallback broker's response (or an empty default), so
   callers do not need to handle a new exception type.

The metrics instance is optional; if not supplied, an isolated instance
is created. Tests inject a fresh instance to assert counters.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

from brokers.common.data_contracts import FundLimits, MarketDepth, Quote
from brokers.common.observability.event_metrics import EventMetrics

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        dhan_gateway=None,
        upstox_gateway=None,
        metrics: Optional[EventMetrics] = None,
    ) -> None:
        self._dhan = dhan_gateway
        self._upstox = upstox_gateway
        self._metrics = metrics or EventMetrics()

    @property
    def dhan(self):
        return self._dhan

    @property
    def upstox(self):
        return self._upstox

    @property
    def metrics(self) -> EventMetrics:
        return self._metrics

    # ── Observability helpers ────────────────────────────────────────────

    def _log_fallback(
        self,
        operation: str,
        broker: str,
        exc: BaseException,
    ) -> None:
        """Record a silent fallback: log + metric, never raise.

        The previous implementation used ``except Exception: pass`` which
        hid systemic broker outages. This helper restores observability
        without changing the caller-visible behavior — the original
        fallback (next broker, or empty default) still runs.
        """
        exc_type = type(exc).__name__
        logger.warning(
            "intelligent_gateway_fallback",
            extra={
                "operation": operation,
                "broker": broker,
                "exception_type": exc_type,
                "exception_message": str(exc),
            },
        )
        # Bucket by (operation, broker, exception_type) so a single noisy
        # broker does not mask a different broker's failure.
        self._metrics.inc(
            "intelligent_gateway_fallback",
            f"{operation}:{broker}:{exc_type}",
        )

    # ── Routing methods ──────────────────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Route to Upstox for faster LTP."""
        if self._upstox:
            try:
                return self._upstox.ltp(symbol, exchange)
            except Exception as exc:
                self._log_fallback("ltp", "upstox", exc)
        if self._dhan:
            return self._dhan.ltp(symbol, exchange)
        raise RuntimeError("No broker available")

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get LTP for multiple symbols using parallel fetching."""
        if self._upstox:
            try:
                return self._upstox.ltp_batch(symbols, exchange)
            except Exception as exc:
                self._log_fallback("ltp_batch", "upstox", exc)
        if self._dhan:
            return self._dhan.ltp_batch(symbols, exchange)
        raise RuntimeError("No broker available")

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Route to Upstox for faster quotes."""
        if self._upstox:
            try:
                return self._upstox.quote(symbol, exchange)
            except Exception as exc:
                self._log_fallback("quote", "upstox", exc)
        if self._dhan:
            return self._dhan.quote(symbol, exchange)
        raise RuntimeError("No broker available")

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Get quotes for multiple symbols using parallel fetching."""
        if self._upstox:
            try:
                return self._upstox.quote_batch(symbols, exchange)
            except Exception as exc:
                self._log_fallback("quote_batch", "upstox", exc)
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
            except Exception as exc:
                self._log_fallback("history", "dhan", exc)
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
            except Exception as exc:
                self._log_fallback("history_batch", "dhan", exc)
        if self._upstox:
            return self._upstox.history_batch(symbols, exchange, timeframe, lookback_days)
        raise RuntimeError("No broker available")

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Route to Dhan (Upstox endpoint deprecated)."""
        if self._dhan:
            try:
                return self._dhan.depth(symbol, exchange)
            except Exception as exc:
                self._log_fallback("depth", "dhan", exc)
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
            except Exception as exc:
                self._log_fallback("option_chain", "dhan", exc)
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
            except Exception as exc:
                self._log_fallback("future_chain", "dhan", exc)
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
            except Exception as exc:
                self._log_fallback("stream", "dhan", exc)
        if self._upstox:
            return self._upstox.stream(symbol, exchange, mode, on_tick)
        raise RuntimeError("No broker available")

    def positions(self) -> list[Any]:
        """Get positions from first available broker."""
        if self._dhan:
            try:
                return self._dhan.positions()
            except Exception as exc:
                self._log_fallback("positions", "dhan", exc)
        if self._upstox:
            return self._upstox.positions()
        return []

    def holdings(self) -> list[Any]:
        """Get holdings from first available broker."""
        if self._dhan:
            try:
                return self._dhan.holdings()
            except Exception as exc:
                self._log_fallback("holdings", "dhan", exc)
        if self._upstox:
            return self._upstox.holdings()
        return []

    def funds(self) -> FundLimits:
        """Get funds from first available broker."""
        if self._dhan:
            try:
                return self._dhan.funds()
            except Exception as exc:
                self._log_fallback("funds", "dhan", exc)
        if self._upstox:
            return self._upstox.funds()
        return FundLimits()

    def trades(self) -> list[Any]:
        """Get trades from first available broker."""
        if self._dhan:
            try:
                return self._dhan.trades()
            except Exception as exc:
                self._log_fallback("trades", "dhan", exc)
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
            except Exception as exc:
                self._log_fallback("search", "dhan", exc)
        if self._upstox:
            return self._upstox.search(query)
        return []
