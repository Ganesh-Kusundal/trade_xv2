"""HistoricalDataLoader — download and store data from brokers.

Uses Dhan/Upstox gateways to fetch historical data and write to Parquet.
Only used for initial load and gap filling — not for research.
"""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import pyarrow as pa

from datalake.io import atomic_parquet_write

logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """Download historical data from brokers and store as Parquet."""

    def __init__(self, root: str = "market_data", catalog=None) -> None:
        self._root = Path(root)
        self._catalog = catalog

    def download_symbol(
        self,
        symbol: str,
        gateway,
        years: int = 5,
        timeframe: str = "1m",
        exchange: str = "NSE",
    ) -> int:
        """Download historical data for a single symbol.

        Parameters
        ----------
        symbol : str
            Symbol to download.
        gateway : MarketDataGateway
            Broker gateway with history() method.
        years : int
            Years of data to fetch.
        timeframe : str
            Timeframe.
        exchange : str
            Exchange.

        Returns
        -------
        Number of rows written.
        """
        try:
            df = gateway.history(symbol, exchange=exchange, timeframe=timeframe, lookback_days=years * 365)
        except Exception as exc:
            logger.error("Failed to download %s: %s", symbol, exc)
            return 0

        if df is None or df.empty:
            logger.warning("No data returned for %s", symbol)
            return 0

        # Normalize to canonical schema
        df = self._normalize(df, symbol, exchange)
        if df.empty:
            return 0

        # Write to Parquet
        rows = self._write_parquet(df, symbol, timeframe)
        logger.info("Downloaded %s: %d rows", symbol, rows)

        # Register in catalog
        if self._catalog and rows > 0:
            ts = pd.to_datetime(df["timestamp"])
            self._catalog.register_symbol(
                symbol=symbol,
                exchange=exchange,
                first_date=ts.min().date(),
                last_date=ts.max().date(),
                total_rows=rows,
                timeframe=timeframe,
                parquet_path=str(self._parquet_path(symbol, timeframe)),
            )

        return rows

    def download_universe(
        self,
        universe: str,
        gateway,
        years: int = 5,
        timeframe: str = "1m",
    ) -> dict[str, int]:
        """Download data for all symbols in a universe.

        Returns
        -------
        Dict mapping symbol → rows written.
        """
        from datalake.schema import UNIVERSE_FILES
        import csv

        path = UNIVERSE_FILES.get(universe)
        if not path:
            logger.error("Unknown universe: %s", universe)
            return {}

        p = Path(path)
        if not p.exists():
            p = self._root.parent / path
        if not p.exists():
            logger.error("Universe file not found: %s", path)
            return {}

        with open(p) as f:
            reader = csv.DictReader(f)
            symbols = [row["symbol"] for row in reader]

        results = {}
        for i, symbol in enumerate(symbols, 1):
            logger.info("[%d/%d] Downloading %s...", i, len(symbols), symbol)
            rows = self.download_symbol(symbol, gateway, years=years, timeframe=timeframe)
            results[symbol] = rows

        total = sum(results.values())
        logger.info("Universe %s: %d symbols, %d total rows", universe, len(results), total)
        return results

    def repair_missing(
        self,
        symbol: str,
        gateway,
        timeframe: str = "1m",
    ) -> int:
        """Download only missing data for a symbol.

        Compares existing Parquet with what's available, downloads gap.
        Returns number of rows added.
        """
        existing_path = self._parquet_path(symbol, timeframe)
        if not existing_path.exists():
            return self.download_symbol(symbol, gateway, years=5, timeframe=timeframe)

        existing = pd.read_parquet(existing_path)
        if existing.empty:
            return self.download_symbol(symbol, gateway, years=5, timeframe=timeframe)

        ts = pd.to_datetime(existing["timestamp"])
        last_date = ts.max()
        days_missing = (datetime.now() - last_date).days

        if days_missing <= 1:
            logger.info("%s: no gaps detected", symbol)
            return 0

        logger.info("%s: downloading %d missing days", symbol, days_missing)
        return self.download_symbol(
            symbol, gateway, years=1, timeframe=timeframe
        )

    def _normalize(
        self, df: pd.DataFrame, symbol: str, exchange: str
    ) -> pd.DataFrame:
        """Normalize broker DataFrame to canonical schema."""
        # Handle different column names from different brokers
        col_map = {
            "bar_time_ms": "timestamp",
            "open_paisa": "open",
            "high_paisa": "high",
            "low_paisa": "low",
            "close_paisa": "close",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Date": "timestamp",
            "Datetime": "timestamp",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Ensure required columns exist
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                logger.warning("Missing column %s, skipping", col)
                return pd.DataFrame()

        # Convert timestamp
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        # Convert paise to rupees if needed (values > 100000 suggest paise)
        for col in ["open", "high", "low", "close"]:
            if df[col].max() > 100000:
                df[col] = df[col] / 100.0

        # Add missing columns
        df["symbol"] = symbol
        df["exchange"] = exchange
        if "oi" not in df.columns:
            df["oi"] = 0

        # Select canonical columns
        canonical = ["timestamp", "symbol", "exchange", "open", "high", "low", "close", "volume", "oi"]
        for col in canonical:
            if col not in df.columns:
                df[col] = 0 if col in ("volume", "oi") else ""

        return df[canonical].dropna(subset=["timestamp"])

    def _write_parquet(
        self, df: pd.DataFrame, symbol: str, timeframe: str
    ) -> int:
        """Write DataFrame to hive-partitioned Parquet atomically."""
        target = self._parquet_path(symbol, timeframe)

        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(target, table, compression="snappy")
        return len(df)

    def _parquet_path(self, symbol: str, timeframe: str = "1m") -> Path:
        return (
            self._root
            / "equities"
            / "candles"
            / f"timeframe={timeframe}"
            / f"symbol={symbol}"
            / "data.parquet"
        )
