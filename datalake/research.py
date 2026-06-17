"""Research API — fast local queries over Parquet + DuckDB.

Provides the primary interface for scanner, strategy, backtest, and analytics.
No broker access required — reads only from local Parquet files.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class ResearchAPI:
    """Fast local data access for research."""

    def __init__(self, root: str = "market_data", catalog=None) -> None:
        self._root = Path(root)
        self._catalog = catalog

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
        parquet_path = self._root / "equities" / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}" / "data.parquet"
        if not parquet_path.exists():
            logger.warning("No data for %s at %s", symbol, parquet_path)
            return pd.DataFrame()

        df = pd.read_parquet(parquet_path)

        # Filter by date range
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"])
            if to_date:
                ts_max = pd.Timestamp(to_date)
                df = df[ts <= ts_max]
                ts = ts[ts <= ts_max]
            if from_date:
                ts_min = pd.Timestamp(from_date)
                df = df[ts >= ts_min]
            elif years:
                cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
                df = df[ts >= cutoff]

        return df.reset_index(drop=True)

    def universe(
        self,
        universe: str = "NIFTY500",
        lookback_days: int = 365,
        timeframe: str = "1m",
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

        Returns
        -------
        Dict mapping symbol → DataFrame.
        """
        symbols = self._load_universe_list(universe)
        from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        result = {}
        for symbol in symbols:
            df = self.history(symbol, timeframe=timeframe, from_date=from_date)
            if not df.empty:
                result[symbol] = df

        return result

    def scan(self, universe: str = "NIFTY500") -> list[str]:
        """List available symbols in a universe that have data."""
        symbols = self._load_universe_list(universe)
        available = []
        for symbol in symbols:
            parquet_path = self._root / "equities" / "candles" / "timeframe=1m" / f"symbol={symbol}" / "data.parquet"
            if parquet_path.exists():
                available.append(symbol)
        return available

    def latest(self, symbol: str, timeframe: str = "1m", n: int = 1) -> pd.DataFrame:
        """Get the latest N candles for a symbol."""
        df = self.history(symbol, years=1, timeframe=timeframe)
        if df.empty:
            return df
        return df.tail(n).reset_index(drop=True)

    def _load_universe_list(self, universe: str) -> list[str]:
        """Load symbol list — DuckDB first, CSV fallback (I-17)."""
        from datalake.schema import load_universe
        return load_universe(universe, catalog=self._catalog)

    def list_available_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all symbols that have Parquet data."""
        candles_dir = self._root / "equities" / "candles" / f"timeframe={timeframe}"
        if not candles_dir.exists():
            return []

        symbols = []
        for sym_dir in candles_dir.iterdir():
            if sym_dir.is_dir() and sym_dir.name.startswith("symbol="):
                symbol = sym_dir.name.replace("symbol=", "")
                if (sym_dir / "data.parquet").exists():
                    symbols.append(symbol)
        return sorted(symbols)
