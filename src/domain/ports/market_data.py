"""MarketDataPort — single port for all historical market data access.

No top-level pandas. Return types use domain series / Any so adapters may
export DataFrames at the analytics boundary without polluting domain imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from domain.entities.options import FutureChain, OptionChain

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries


@runtime_checkable
class MarketDataPort(Protocol):
    """Canonical historical-data contract for analytics/replay/backtest.

    Prefer :class:`~domain.candles.historical.HistoricalSeries`. Legacy
    adapters may still return a DataFrame object at the boundary.
    """

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> "HistoricalSeries | Any":
        """Load historical OHLCV bars for *symbol*."""
        ...

    def option_chain(
        self,
        underlying: str,
        *,
        expiry: str | None = None,
    ) -> OptionChain:
        """Load option chain for *underlying*."""
        ...

    def future_chain(self, underlying: str) -> FutureChain:
        """Load futures chain for *underlying*."""
        ...

    def ltp(self, symbol: str, *, exchange: str = "NSE") -> float:
        """Return last-traded price for *symbol*."""
        ...

    def history_batch(
        self,
        symbols: list[str],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> "HistoricalSeries | Any":
        """Load historical OHLCV for multiple symbols."""
        ...

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all symbols that have data for *timeframe*."""
        ...

    def query(self, sql: str, params: list | None = None) -> Any:
        """Analytical SQL escape hatch (returns tabular export at boundary)."""
        ...


__all__ = ["MarketDataPort"]
