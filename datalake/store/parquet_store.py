"""Parquet candle store — deep module for datalake loading and resampling."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pandas as pd
from cachetools import TTLCache

from datalake.cache_utils import generate_cache_key
from datalake.symbols import normalize_symbol, symbol_to_path

logger = logging.getLogger(__name__)


class ParquetStore:
    """Load and resample OHLCV candles from the local parquet lake."""

    def __init__(self, root: str = "market_data") -> None:
        self._root = Path(root)
        self._candles_dir = self._root / "equities" / "candles"
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

    def parquet_path(self, symbol: str, timeframe: str) -> Path:
        return self._candles_dir / f"timeframe={timeframe}" / symbol_to_path(symbol) / "data.parquet"

    def load_candles(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Load candles for *symbol* at *timeframe*, resampling from 1m when needed."""
        symbol = normalize_symbol(symbol)
        path = self.parquet_path(symbol, timeframe)
        if path.exists():
            try:
                return pd.read_parquet(path)
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

        resampled = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
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
