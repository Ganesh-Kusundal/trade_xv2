"""Incremental Updater — keep data lake up to date with daily downloads."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.io import atomic_parquet_write
from brokers.common.batch_executor import batch_execute

logger = logging.getLogger(__name__)


class IncrementalUpdater:
    """Incrementally update the data lake with new data."""

    def __init__(self, root: str = "market_data", catalog=None, loader=None) -> None:
        self._root = Path(root)
        self._catalog = catalog
        self._loader = loader

    def update_daily(
        self,
        gateway,
        universe: str = "NIFTY500",
        timeframe: str = "1m",
    ) -> dict[str, int]:
        """Update all symbols with today's data.

        Returns
        -------
        Dict mapping symbol → rows added.
        """
        import csv

        from datalake.schema import UNIVERSE_FILES

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

        def _update_one(sym: str) -> int:
            return self._update_symbol(sym, gateway, timeframe)

        def _on_error(sym: str, exc: Exception) -> None:
            logger.error("Failed to update %s: %s", sym, exc)

        results = batch_execute(
            symbols, _update_one, on_error=_on_error,
        )

        total = sum(results.values())
        logger.info("Update complete: %d symbols, %d new rows", len(results), total)
        return results

    def _update_symbol(
        self,
        symbol: str,
        gateway,
        timeframe: str,
    ) -> int:
        """Update a single symbol with latest data."""
        parquet_path = (
            self._root
            / "equities"
            / "candles"
            / f"timeframe={timeframe}"
            / f"symbol={symbol}"
            / "data.parquet"
        )

        if not parquet_path.exists():
            # No existing data, do full download
            return self._loader.download_symbol(symbol, gateway, years=1, timeframe=timeframe)

        # Get last date in existing data
        try:
            existing = pd.read_parquet(parquet_path, columns=["timestamp"])
            last_date = pd.to_datetime(existing["timestamp"]).max()
            days_missing = (datetime.now() - last_date).days
        except Exception:
            days_missing = 1

        if days_missing <= 0:
            return 0

        # Download missing days
        try:
            df = gateway.history(symbol, timeframe=timeframe, lookback_days=days_missing + 1)
        except Exception as exc:
            logger.warning("Failed to update %s: %s", symbol, exc)
            return 0

        if df is None or df.empty:
            return 0

        # Normalize
        df = self._loader._normalize(df, symbol, "NSE")
        if df.empty:
            return 0

        # Append to existing
        try:
            existing = pd.read_parquet(parquet_path)
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
            table = pa.Table.from_pandas(combined, preserve_index=False)
            atomic_parquet_write(parquet_path, table, compression="snappy")
            return len(combined) - len(existing)
        except Exception as exc:
            logger.warning("Failed to append data for %s: %s", symbol, exc)
            return 0
