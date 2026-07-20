"""Parquet candle store — deep module for datalake loading and resampling."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import duckdb
import pandas as pd
from cachetools import TTLCache, cached

from datalake.core.paths import CURATED_ROOT, curated_equity_glob, curated_equity_path
from datalake.core.symbols import normalize_symbol_for_storage, symbol_to_path
from datalake.storage.cache_utils import generate_cache_key

logger = logging.getLogger(__name__)

# Module-level TTL cache for curated candle loads.
# Keyed by (curated_root, symbol, timeframe) so different store roots
# (e.g. in tests) do not collide.
_curated_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)  # 5-minute TTL
_curated_cache_lock = threading.Lock()


class ParquetStore:
    """Load and resample OHLCV candles from the local parquet lake."""

    def __init__(self, root: str | None = None, curated_root: str = CURATED_ROOT) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS

            root = DEFAULT_DATA_PATHS.lake_root
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

    @cached(
        cache=_curated_cache,
        key=lambda self, symbol, timeframe: (str(self._curated_root), symbol, timeframe),
        lock=_curated_cache_lock,
    )
    def load_curated_candles(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Load candles from the date-partitioned curated layout using DuckDB.

        Returns None silently if curated layout doesn't exist yet.
        """
        symbol = normalize_symbol_for_storage(symbol)

        # Skip if curated layout doesn't exist
        curated_dir = curated_equity_path(root=str(self._curated_root))
        if not curated_dir.exists():
            return None

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

    def invalidate_curated_cache(self) -> None:
        """Clear the curated candles cache.

        Call this when underlying parquet data is refreshed or updated.
        """
        with _curated_cache_lock:
            _curated_cache.clear()

    def load_candles(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Load candles for *symbol* at *timeframe*, resampling from 1m when needed.

        Checks the curated (date-partitioned) layout first, then falls
        back to the legacy symbol-per-file layout.
        """
        symbol = normalize_symbol_for_storage(symbol)

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
        """List all symbols, trying curated layout first, then legacy.

        P2-5 fix: Removed expensive filesystem glob check. Tries DuckDB
        query directly, which is faster and avoids scanning the directory tree.
        """
        # Try curated layout via DuckDB (no filesystem glob check)
        try:
            import duckdb

            glob_pattern = curated_equity_glob(root=str(self._curated_root))
            df = duckdb.execute(
                "SELECT DISTINCT symbol FROM read_parquet(?) ORDER BY symbol",
                [glob_pattern],
            ).fetchdf()
            if not df.empty:
                return df["symbol"].tolist()
        except Exception as exc:
            logger.debug("Curated list_symbols failed, trying legacy: %s", exc)

        # Fallback to legacy layout
        tf_dir = self._candles_dir / f"timeframe={timeframe}"
        if not tf_dir.exists():
            return []
        return sorted(
            p.name.replace("symbol=", "")
            for p in tf_dir.iterdir()
            if p.is_dir() and p.name.startswith("symbol=")
        )
