"""HistoricalDataLoader — download and store data from brokers.

Uses Dhan/Upstox gateways to fetch historical data and write to Parquet.
Only used for initial load and gap filling — not for research.

All timestamps are normalized to IST (naive datetime) before writing.
All symbols are normalized (uppercased, stripped) before writing.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.io import atomic_parquet_write
from datalake.schema import CANONICAL_COLUMNS, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE
from datalake.symbols import normalize_symbol
from datalake.validation import validate_candles

logger = logging.getLogger(__name__)

# NSE trading hours
NSE_MARKET_OPEN = dt_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)  # 09:15
NSE_MARKET_CLOSE = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)  # 15:30
EXPECTED_CANDLES_PER_DAY = 375  # 1-minute candles for full trading day


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
    ) -> dict:
        """Download historical data for a single symbol.

        Returns
        -------
        Dict with keys: rows, duplicates_dropped, invalid_dropped.
        """
        symbol = normalize_symbol(symbol)
        try:
            df = gateway.history(symbol, exchange=exchange, timeframe=timeframe, lookback_days=years * 365)
        except Exception as exc:
            logger.error("Failed to download %s: %s", symbol, exc)
            return {"rows": 0, "duplicates_dropped": 0, "invalid_dropped": 0}

        if df is None or df.empty:
            logger.warning("No data returned for %s", symbol)
            return {"rows": 0, "duplicates_dropped": 0, "invalid_dropped": 0}

        df = self._normalize(df, symbol, exchange)
        if df.empty:
            return {"rows": 0, "duplicates_dropped": 0, "invalid_dropped": 0}

        # Dedup with logging
        len(df)
        dup_count = df.duplicated(subset=["timestamp"]).sum()
        if dup_count > 0:
            logger.warning("%s: dropping %d duplicate timestamps", symbol, dup_count)
        df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")

        # Validate intraday completeness
        if timeframe in ("1m", "5m", "15m", "30m"):
            completeness = self._check_intraday_completeness(df, timeframe)
            if completeness < 0.90:  # Less than 90% complete
                logger.warning(
                    "%s: Intraday completeness only %.1f%% (expected ~375 candles/day for 1m)",
                    symbol, completeness * 100
                )

        # Write to Parquet
        rows, invalid = self._write_parquet(df, symbol, timeframe)
        logger.info("Downloaded %s: %d rows (%d invalid dropped)", symbol, rows, invalid)

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

        return {
            "rows": rows,
            "duplicates_dropped": dup_count,
            "invalid_dropped": invalid,
        }

    def download_universe(
        self,
        universe: str,
        gateway,
        years: int = 5,
        timeframe: str = "1m",
    ) -> dict[str, dict[str, int]]:
        """Download data for all symbols in a universe."""
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

        results = {}
        for i, symbol in enumerate(symbols, 1):
            logger.info("[%d/%d] Downloading %s...", i, len(symbols), symbol)
            results[normalize_symbol(symbol)] = self.download_symbol(
                symbol, gateway, years=years, timeframe=timeframe
            )

        total_rows = sum(r["rows"] for r in results.values())
        logger.info("Universe %s: %d symbols, %d total rows", universe, len(results), total_rows)
        return results

    def repair_missing(
        self,
        symbol: str,
        gateway,
        timeframe: str = "1m",
    ) -> int:
        """Download only missing data for a symbol.

        Uses actual candle count comparison, not just last date,
        to detect gaps within the date range.
        """
        symbol = normalize_symbol(symbol)
        existing_path = self._parquet_path(symbol, timeframe)
        if not existing_path.exists():
            return self.download_symbol(symbol, gateway, years=5, timeframe=timeframe)["rows"]

        try:
            existing = pd.read_parquet(existing_path)
        except Exception:
            return self.download_symbol(symbol, gateway, years=5, timeframe=timeframe)["rows"]

        if existing.empty:
            return self.download_symbol(symbol, gateway, years=5, timeframe=timeframe)["rows"]

        ts = pd.to_datetime(existing["timestamp"])
        last_date = ts.max()
        days_missing = (datetime.now() - last_date).days

        # Check for incomplete last day
        incomplete_day = False
        if timeframe in ("1m", "5m", "15m", "30m"):
            last_day_candles = (ts.dt.date == last_date.date()).sum()
            candles_per_hour = 60 // int(timeframe.replace("m", "").replace("h", "60"))
            expected_last_day = int(candles_per_hour * 6.25)
            if last_day_candles < expected_last_day * 0.90:  # Less than 90%
                incomplete_day = True
                logger.warning(
                    "%s: Last day incomplete (%d/%d candles)",
                    symbol, last_day_candles, expected_last_day
                )

        if days_missing <= 1 and not incomplete_day:
            logger.info("%s: no gaps detected", symbol)
            return 0

        logger.info("%s: downloading %d missing days", symbol, days_missing)
        return self.download_symbol(symbol, gateway, years=1, timeframe=timeframe)["rows"]

    def _normalize(
        self, df: pd.DataFrame, symbol: str, exchange: str
    ) -> pd.DataFrame:
        """Normalize broker DataFrame to canonical schema (IST timestamps)."""
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

        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                logger.warning("Missing column %s, skipping", col)
                return pd.DataFrame()

        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        # Convert paise to rupees if needed
        for col in ["open", "high", "low", "close"]:
            if df[col].max() > 100000:
                df[col] = df[col] / 100.0

        df["symbol"] = symbol
        df["exchange"] = exchange
        if "oi" not in df.columns:
            df["oi"] = 0

        for col in CANONICAL_COLUMNS:
            if col not in df.columns:
                df[col] = 0 if col in ("volume", "oi") else ""
        df = df[CANONICAL_COLUMNS].dropna(subset=["timestamp"])

        # Validate (drops invalid rows, logs)
        df = validate_candles(df, symbol=symbol, drop_invalid=True)

        return df

    def _write_parquet(
        self, df: pd.DataFrame, symbol: str, timeframe: str
    ) -> tuple[int, int]:
        """Write DataFrame to hive-partitioned Parquet atomically."""
        target = self._parquet_path(symbol, timeframe)

        invalid_count = 0
        before = len(df)
        df = validate_candles(df, symbol=symbol, drop_invalid=True)
        invalid_count = before - len(df)

        table = pa.Table.from_pandas(df, preserve_index=False)
        atomic_parquet_write(target, table, compression="snappy")
        return len(df), invalid_count

    def _parquet_path(self, symbol: str, timeframe: str = "1m") -> Path:
        from datalake.symbols import symbol_to_path
        return (
            self._root
            / "equities"
            / "candles"
            / f"timeframe={timeframe}"
            / symbol_to_path(symbol)
            / "data.parquet"
        )

    def _check_intraday_completeness(self, df: pd.DataFrame, timeframe: str) -> float:
        """Check intraday data completeness.

        Returns
        -------
        float
            Completeness ratio (0.0 to 1.0) based on expected candles per day.
        """
        if df.empty or "timestamp" not in df.columns:
            return 0.0

        # Calculate expected candles per day based on timeframe
        candles_per_hour = 60 // int(timeframe.replace("m", "").replace("h", "60"))
        trading_hours = 6.25  # 9:15 to 15:30 = 6.25 hours
        expected_per_day = int(candles_per_hour * trading_hours)

        # Group by date and count candles
        ts = pd.to_datetime(df["timestamp"])
        daily_counts = ts.groupby(ts.dt.date).count()

        if len(daily_counts) == 0:
            return 0.0

        # Calculate average completeness
        avg_candles = daily_counts.mean()
        completeness = min(avg_candles / expected_per_day, 1.0)

        return completeness
