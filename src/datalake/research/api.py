"""Research API — fast local queries over Parquet + DuckDB.

Provides the primary interface for scanner, strategy, backtest, and analytics.
No broker access required — reads only from local Parquet files.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from datalake.core.paths import timeframe_partition_dir
from datalake.gateway import DataLakeGateway
from datalake.core.paths import CURATED_ROOT

logger = logging.getLogger(__name__)


class ResearchAPI:
    """Fast local data access for research."""

    def __init__(
        self, root: str = "market_data", curated_root: str = CURATED_ROOT, catalog=None
    ) -> None:
        self._root = Path(root)
        self._curated_root = Path(curated_root)
        self._catalog = catalog
        # Delegate to DataLakeGateway for unified data access path
        self._gateway = DataLakeGateway(root=str(self._root), curated_root=str(self._curated_root))

    def history(
        self,
        symbol: str,
        years: int = 5,
        timeframe: str = "1m",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV data for a symbol.

        Parameters
        ----------
        symbol : str
            NSE symbol (e.g., "RELIANCE").
        years : int
            Years of history to load.
        timeframe : str
            Candle timeframe.
        from_date : str or None
            Start date (YYYY-MM-DD). Overrides years.
        to_date : str or None
            End date (YYYY-MM-DD). Default: today.

        Returns
        -------
        pd.DataFrame with canonical columns.
        """
        # Delegate to DataLakeGateway for unified Parquet access
        lookback_days = years * 365 if not from_date else 0
        df = self._gateway.history(
            symbol,
            exchange="NSE",
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )
        return df.reset_index(drop=True) if not df.empty else df

    def universe(
        self,
        universe: str = "NIFTY500",
        lookback_days: int = 365,
        timeframe: str = "1m",
        as_of_date: str | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Load data for all symbols in a universe.

        Parameters
        ----------
        universe : str
            Universe name (NIFTY50, NIFTY100, NIFTY200, NIFTY500).
        lookback_days : int
            Days of history to load.
        timeframe : str
            Candle timeframe.
        as_of_date : str or None
            Historical date (YYYY-MM-DD) for point-in-time universe membership.

        Returns
        -------
        Dict mapping symbol → DataFrame.
        """
        symbols = self._load_universe_list(universe, as_of_date=as_of_date)
        from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        result = {}
        for symbol in symbols:
            df = self.history(symbol, timeframe=timeframe, from_date=from_date)
            if not df.empty:
                result[symbol] = df

        return result

    def scan(self, universe: str = "NIFTY500", as_of_date: str | None = None) -> list[str]:
        """List available symbols in a universe that have data."""
        symbols = self._load_universe_list(universe, as_of_date=as_of_date)
        available = []
        for symbol in symbols:
            df = self._gateway.history(symbol, exchange="NSE", timeframe="1m", lookback_days=1)
            if not df.empty:
                available.append(symbol)
        return available

    def latest(self, symbol: str, timeframe: str = "1m", n: int = 1) -> pd.DataFrame:
        """Get the latest N candles for a symbol."""
        df = self.history(symbol, years=1, timeframe=timeframe)
        if df.empty:
            return df
        return df.tail(n).reset_index(drop=True)

    def _load_universe_list(self, universe: str, as_of_date: str | None = None) -> list[str]:
        """Load symbol list — DuckDB first, CSV fallback (I-17)."""
        from datetime import date

        from datalake.core.schema import load_universe

        parsed: date | None = None
        if as_of_date is not None:
            parsed = date.fromisoformat(as_of_date)
        return load_universe(universe, catalog=self._catalog, as_of_date=parsed)

    def list_available_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all symbols that have Parquet data."""
        candles_dir = timeframe_partition_dir(str(self._root), timeframe)
        if not candles_dir.exists():
            return []

        symbols = []
        for sym_dir in candles_dir.iterdir():
            if sym_dir.is_dir() and sym_dir.name.startswith("symbol="):
                symbol = sym_dir.name.replace("symbol=", "")
                if (sym_dir / "data.parquet").exists():
                    symbols.append(symbol)
        return sorted(symbols)
