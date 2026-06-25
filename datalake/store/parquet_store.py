"""Parquet candle store — deep module for datalake loading and resampling."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import duckdb
import pandas as pd
from cachetools import TTLCache

from datalake.cache_utils import generate_cache_key
from datalake.paths import CURATED_ROOT, curated_equity_glob, curated_equity_path
from datalake.symbols import normalize_symbol, symbol_to_path

logger = logging.getLogger(__name__)


class ParquetStore:
    """Load and resample OHLCV candles from the local parquet lake."""

    def __init__(self, root: str = "market_data", curated_root: str = CURATED_ROOT) -> None:
        self._root = Path(root)
        self._candles_dir = self._root / "equities" / "candles"
        self._curated_root = Path(curated_root)
        self._resample_cache: TTLCache = TTLCache(
            maxsize=100,
            ttl=300,
        )
        self._resample_cache_lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def candles_dir(self) -> Path:
        return self._candles_dir

    @property
    def curated_root(self) -> Path:
        return self._curated_root

    def parquet_path(self, symbol: str, timeframe: str) -> Path:
        return (
            self._candles_dir / f"timeframe={timeframe}" / symbol_to_path(symbol) / "data.parquet"
        )

    def _layout_in_use(self) -> str:
        """Detect which partition layout is present on disk.

        Returns ``"curated"``, ``"legacy"``, or ``"none"``.
        """
        curated_dir = curated_equity_path(root=str(self._curated_root))
        if curated_dir.exists():
            return "curated"
        legacy_dir = self._candles_dir / "timeframe=1m"
        if legacy_dir.exists():
            return "legacy"
        return "none"

    def load_curated_candles(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Load candles from the date-partitioned curated layout using DuckDB."""
        symbol = normalize_symbol(symbol)
        glob_pattern = curated_equity_glob(root=str(self._curated_root))
        try:
            query = """
                SELECT *
                FROM read_parquet(?)
                WHERE symbol = ?
            """
            df = duckdb.execute(query, [glob_pattern, symbol]).fetchdf()
            if df.empty:
                return None
            if "timestamp" in df.columns:
                df = df.sort_values("timestamp").reset_index(drop=True)
            return df
        except Exception as exc:
            logger.error("Failed to read curated candles for %s: %s", symbol, exc)
            return None

    def load_candles(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Load candles for *symbol* at *timeframe*, resampling from 1m when needed.

        Checks the curated (date-partitioned) layout first, then falls
        back to the legacy symbol-per-file layout.
        """
        symbol = normalize_symbol(symbol)

        curated_df = self.load_curated_candles(symbol, timeframe)
        if curated_df is not None and not curated_df.empty:
            if timeframe == "1m":
                return curated_df
            return self.resample(curated_df, timeframe)

        path = self.parquet_path(symbol, timeframe)
        if path.exists():
            try:
                df = pd.read_parquet(path)
                if timeframe == "1m":
                    return df
                return self.resample(df, timeframe)
            except Exception as exc:
                logger.error("Failed to read %s: %s", path, exc)
                return None

        if timeframe != "1m":
            df_1m = self.load_candles(symbol, "1m")
            if df_1m is not None and not df_1m.empty:
                return self.resample(df_1m, timeframe)

        logger.warning("No data for %s/%s", symbol, timeframe)
        return None

    def resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if df.empty:
            return df

        symbol = df["symbol"].iloc[0] if "symbol" in df.columns else ""
        cache_key = generate_cache_key(symbol, timeframe)

        with self._resample_cache_lock:
            if cache_key in self._resample_cache:
                return self._resample_cache[cache_key].copy()

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        rule_map = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "1D": "1D"}
        rule = rule_map.get(timeframe)
        if not rule:
            return df.reset_index()

        resampled = (
            df.resample(rule)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
        if "symbol" in df.columns:
            resampled["symbol"] = symbol

        resampled = resampled.reset_index()
        with self._resample_cache_lock:
            self._resample_cache[cache_key] = resampled.copy()
        return resampled

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        tf_dir = self._candles_dir / f"timeframe={timeframe}"
        if not tf_dir.exists():
            return []
        return sorted(
            p.name.replace("symbol=", "")
            for p in tf_dir.iterdir()
            if p.is_dir() and p.name.startswith("symbol=")
        )
