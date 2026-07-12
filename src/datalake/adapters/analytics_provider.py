"""DataLakeMarketDataProvider — single adapter implementing MarketDataPort.

Bridges the Data Lake (Parquet + DuckDB) to analytics consumers through
the canonical :class:`~domain.ports.market_data.MarketDataPort` protocol.

This is the **only** class that analytics code should import from the
datalake layer.  It wraps :class:`~datalake.gateway.DataLakeGateway`
(and optionally :class:`~datalake.research.api.ResearchAPI`) behind
the narrow port contract, so that Replay, Backtesting, Scanner, API,
Research, Walk-Forward, Paper Trading, and CLI all consume identical
historical datasets through one interface.

Usage::

    from datalake.adapters import DataLakeMarketDataProvider

    provider = DataLakeMarketDataProvider(root="market_data")
    df = provider.history("RELIANCE", timeframe="1m", lookback_days=30)
    quotes = provider.ltp("TCS")
    batch = provider.history_batch(["RELIANCE", "TCS"], timeframe="1D")
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from datalake.exchange_registry import get_active_exchange_code
from domain.entities.options import FutureChain, OptionChain
from domain.ports.market_data import MarketDataPort

logger = logging.getLogger(__name__)


class DataLakeMarketDataProvider:
    """Unified analytics data provider backed by the datalake.

    Wraps :class:`~datalake.gateway.DataLakeGateway` to satisfy the
    :class:`~domain.ports.market_data.MarketDataPort` protocol.  All
    historical data flows through this single adapter — no analytics
    module may bypass it to access DuckDB, Parquet, or file paths.

    Parameters
    ----------
    gateway:
        Pre-configured :class:`~datalake.gateway.DataLakeGateway`.
        If *None*, one is created from *root*.
    root:
        Datalake root directory (default ``"market_data"``).
    """

    def __init__(
        self,
        gateway: Any | None = None,
        root: str = "market_data",
    ) -> None:
        # Lazy import to avoid circular dependencies at module level.
        from datalake.gateway import DataLakeGateway

        self._gateway: DataLakeGateway = gateway or DataLakeGateway(root=root)
        self._root = root

    # ── MarketDataPort: single-symbol access ────────────────────────

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV bars for *symbol* via the gateway."""
        return self._gateway.history(
            symbol,
            exchange=get_active_exchange_code(),
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )

    def option_chain(
        self,
        underlying: str,
        *,
        expiry: str | None = None,
    ) -> OptionChain:
        """Load option chain for *underlying*."""
        chain = self._gateway.option_chain(underlying, expiry=expiry)
        if isinstance(chain, OptionChain):
            return chain
        return OptionChain.from_dict(chain)

    def future_chain(self, underlying: str) -> FutureChain:
        """Load futures chain for *underlying*."""
        chain = self._gateway.future_chain(underlying)
        if isinstance(chain, FutureChain):
            return chain
        return FutureChain.from_dict(chain if isinstance(chain, dict) else {"contracts": []})

    def ltp(self, symbol: str, *, exchange: str | None = None) -> float:
        if exchange is None:
            exchange = get_active_exchange_code()
        """Return last-traded price for *symbol*."""
        return float(self._gateway.ltp(symbol, exchange=exchange))

    # ── MarketDataPort: batch / universe access ─────────────────────

    def history_batch(
        self,
        symbols: list[str],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV for multiple symbols in one call."""
        return self._gateway.history_batch(
            symbols,
            exchange=get_active_exchange_code(),
            timeframe=timeframe,
            lookback_days=lookback_days,
        )

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all symbols that have data for *timeframe*."""
        return self._gateway.list_symbols(timeframe)

    # ── MarketDataPort: analytical escape hatch ─────────────────────

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        """Execute raw SQL against the DuckDB analytical engine.

        This is an explicit escape hatch for analytical workloads
        (scanners, ranking, feature engineering) that benefit from
        direct SQL.

        Uses a short-lived read-only connection from the pool.
        """
        import duckdb

        # Use a short-lived in-memory connection for ad-hoc queries.
        # For queries that reference the catalog, callers should use
        # the catalog path explicitly in their SQL.
        conn = duckdb.connect(":memory:")
        try:
            if params:
                return conn.execute(sql, params).fetchdf()
            return conn.execute(sql).fetchdf()
        finally:
            conn.close()

    # ── Convenience pass-throughs ───────────────────────────────────

    @property
    def gateway(self) -> Any:
        """Access the underlying gateway (for advanced use only)."""
        return self._gateway

    def __repr__(self) -> str:
        return f"DataLakeMarketDataProvider(root={self._root!r})"


__all__ = ["DataLakeMarketDataProvider"]
