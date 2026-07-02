"""DataLakeGateway — read-only market-data access backed by a Parquet lake.

Composes the narrow ISP interfaces (:class:`MarketDataProvider`,
:class:`BatchMarketDataProvider`,
:class:`InstrumentProvider`, :class:`LifecycleAware`) instead of the
full :class:`~brokers.common.gateway.MarketDataGateway` contract.

This avoids the Liskov-substitution violation (REF-18) where a read-only
implementation was forced to ``raise NotImplementedError`` for trading
and portfolio methods.

Used for backtesting, research, and offline analysis.

Usage:
    from datalake.gateway import DataLakeGateway
    from analytics.backtest import BacktestEngine, BacktestConfig
    from analytics.strategy import StrategyPipeline, MomentumStrategy

    gw = DataLakeGateway(root="market_data")
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    engine = BacktestEngine(strategy, gw)
    result = engine.run("RELIANCE", years=5, timeframe="1D")
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any

import duckdb
import pandas as pd
from cachetools import TTLCache

from brokers.common.gateway import BrokerCapabilities
from brokers.common.gateway_errors import (
    UnsupportedGatewayOperationError,
)
from brokers.common.gateway_interfaces import (
    BatchMarketDataProvider,
    InstrumentProvider,
    LifecycleAware,
    MarketDataProvider,
)
from datalake.storage.cache_utils import get_last_candle_fast
from datalake.core.paths import CURATED_ROOT, curated_equity_glob
from datalake.storage.parquet_store import ParquetStore
from datalake.core.symbols import normalize_symbol
from domain import MarketDepth, Quote
from domain.constants import BATCH_MAX_WORKERS

logger = logging.getLogger(__name__)


class DataLakeGateway(
    MarketDataProvider,
    BatchMarketDataProvider,
    InstrumentProvider,
    LifecycleAware,
):
    """Read-only market-data access backed by local Parquet data lake.

    Composes four narrow ISP interfaces instead of the full
    ``MarketDataGateway`` contract. Trading and portfolio methods are
    intentionally absent — use a live broker gateway for those.
    """

    def __init__(
        self,
        root: str = "market_data",
        curated_root: str = CURATED_ROOT,
        store: ParquetStore | None = None,
    ) -> None:
        self._store = store or ParquetStore(root, curated_root=curated_root)
        self._root = self._store.root
        self._curated_root = self._store.curated_root
        self._candles_dir = self._store.candles_dir
        self._download_pool_max_workers = 4
        # TTL cache for quote() — avoids repeated parquet reads for the
        # same symbol within 5 minutes.  Key: (symbol, exchange).
        self._quote_cache: TTLCache = TTLCache(
            maxsize=512,
            ttl=300,
        )
        self._quote_cache_lock = threading.Lock()

    @staticmethod
    def _df_size(df: pd.DataFrame) -> int:
        """Calculate memory size of a DataFrame in bytes."""
        return int(df.memory_usage(deep=True).sum())

    def _load_parquet(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        return self._store.load_candles(symbol, timeframe)

    def query_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        from_ts: pd.Timestamp | None = None,
        to_ts: pd.Timestamp | None = None,
        limit: int = 5000,
    ) -> pd.DataFrame:
        """Efficiently query candles with predicate pushdown via DuckDB.

        Pushes symbol, timestamp, and LIMIT filters into the Parquet scan
        instead of loading the entire file into Pandas first.

        P0-3 fix: Removed expensive filesystem glob check that scanned the
        directory tree on every call. Now tries curated layout via DuckDB
        first, then falls back to legacy paths — both with full predicate
        and projection pushdown.

        Falls back to :meth:`_load_parquet` + Pandas filtering when DuckDB
        is unavailable or the query fails.
        """
        symbol = normalize_symbol(symbol)
        if timeframe != "1m":
            multiplier = 1
            if timeframe.endswith("m"):
                try:
                    multiplier = int(timeframe[:-1])
                except ValueError:
                    pass
            elif timeframe.endswith("h"):
                try:
                    multiplier = int(timeframe[:-1]) * 60
                except ValueError:
                    pass
            elif timeframe == "1D":
                multiplier = 375

            df_1m = self.query_candles(
                symbol,
                "1m",
                from_ts=from_ts,
                to_ts=to_ts,
                limit=limit * multiplier,
            )
            if df_1m.empty:
                return df_1m

            # Inline resampling to completely bypass ParquetStore cache collisions
            df_1m = df_1m.copy()
            df_1m["timestamp"] = pd.to_datetime(df_1m["timestamp"])
            df_1m = df_1m.set_index("timestamp")

            rule_map = {
                "3m": "3min",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "1h": "1h",
                "4h": "4h",
                "1D": "1D",
            }
            rule = rule_map.get(timeframe, f"{timeframe[:-1]}min" if timeframe.endswith("m") else "5min")

            agg_dict = {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
            if "oi" in df_1m.columns:
                agg_dict["oi"] = "last"

            df_resampled = (
                df_1m.resample(rule)
                .agg(agg_dict)
                .dropna()
            )
            df_resampled = df_resampled.reset_index()
            return df_resampled.tail(limit).reset_index(drop=True)

        try:
            # Build parquet path list (curated + legacy)
            parquet_paths = self._legacy_parquet_paths([symbol], timeframe)
            curated_glob = curated_equity_glob(root=str(self._curated_root))

            # P0-3 fix: Build WHERE clause with predicate pushdown.
            # DuckDB pushes these filters into the parquet scan, avoiding
            # full file reads.
            conditions = ["symbol = ?"]
            params: list = [symbol]

            if from_ts is not None:
                conditions.append("timestamp >= ?")
                params.append(from_ts)
            if to_ts is not None:
                conditions.append("timestamp <= ?")
                params.append(to_ts)

            where_clause = " AND ".join(conditions)

            # Try curated layout first (uses DuckDB to check, not filesystem glob)
            try:
                query = f"""
                    SELECT timestamp, open, high, low, close, volume, oi
                    FROM read_parquet(?)
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params_with_limit = [curated_glob] + params + [limit]
                df = duckdb.execute(query, params_with_limit).fetchdf()
                if not df.empty:
                    return df.sort_values("timestamp").reset_index(drop=True)
            except Exception as exc:
                logger.debug("Curated layout query failed, trying legacy: %s", exc)

            # Fall back to legacy parquet paths
            if parquet_paths:
                source = parquet_paths[0] if len(parquet_paths) == 1 else parquet_paths
                query = f"""
                    SELECT timestamp, open, high, low, close, volume, oi
                    FROM read_parquet(?)
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params_with_limit = [source] + params + [limit]
                df = duckdb.execute(query, params_with_limit).fetchdf()

                if df.empty:
                    return df

                # Return sorted ascending (chronological order)
                return df.sort_values("timestamp").reset_index(drop=True)

            return pd.DataFrame()

        except Exception as exc:
            logger.debug("query_candles DuckDB failed, falling back: %s", exc)
            # Fallback to full load + Pandas filter
            df = self._load_parquet(symbol, timeframe)
            if df is None or df.empty:
                return pd.DataFrame()
            if "timestamp" not in df.columns:
                df["timestamp"] = df.index
            if from_ts is not None:
                df = df[df["timestamp"] >= from_ts]
            if to_ts is not None:
                df = df[df["timestamp"] <= to_ts]
            return df.sort_values("timestamp").tail(limit).reset_index(drop=True)

    def _resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        return self._store.resample(df, timeframe)

    def _filter_by_date(
        self,
        df: pd.DataFrame,
        from_date: str | None = None,
        to_date: str | None = None,
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        if df.empty:
            return df

        ts = pd.to_datetime(df["timestamp"])
        end = pd.Timestamp(to_date) if to_date else ts.max()
        start = pd.Timestamp(from_date) if from_date else end - pd.Timedelta(days=lookback_days)

        mask = (ts >= start) & (ts <= end)
        return df[mask].copy()

    # -----------------------------------------------------------------------
    # MarketDataGateway — Market Data
    # -----------------------------------------------------------------------

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        if isinstance(symbol, list):
            frames = [
                self.history(s, exchange, timeframe, lookback_days, from_date, to_date)
                for s in symbol
            ]
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        symbol = normalize_symbol(symbol)
        df = self._load_parquet(symbol, timeframe)
        if df is None or df.empty:
            return pd.DataFrame()

        df = self._filter_by_date(df, from_date, to_date, lookback_days)
        if not df.empty:
            df["exchange"] = exchange
            df["timeframe"] = timeframe
            # Add canonical instrument_id column
            from datalake.core.symbols import instrument_id_from_symbol
            df["instrument_id"] = instrument_id_from_symbol(symbol, exchange)
        return df

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Return latest OHLCV quote from the most recent 1-minute candle.

        Results are cached for 5 minutes (TTLCache, maxsize=512).
        bid/ask are always None — OHLCV parquet has no order book data.
        """

        symbol = normalize_symbol(symbol)
        cache_key = (symbol, exchange)

        # Check per-instance TTL cache first
        with self._quote_cache_lock:
            cached = self._quote_cache.get(cache_key)
        if cached is not None:
            return cached

        result = self._compute_quote(symbol, exchange)

        # Store in TTL cache
        with self._quote_cache_lock:
            self._quote_cache[cache_key] = result

        return result

    def _compute_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Internal: compute a fresh Quote from parquet data (no cache)."""
        from domain import Quote as _Quote

        df = self._load_parquet(symbol, "1m")
        if df is None or df.empty:
            return _Quote(symbol=symbol)
        last = df.iloc[-1]
        prev_close = df.iloc[-2]["close"] if len(df) > 1 else last["close"]
        return _Quote(
            symbol=symbol,
            ltp=Decimal(str(last["close"])),
            open=Decimal(str(last["open"])),
            high=Decimal(str(last["high"])),
            low=Decimal(str(last["low"])),
            close=Decimal(str(last["close"])),
            volume=int(last["volume"]),
            change=Decimal(str(last["close"] - prev_close)),
            # Note: bid/ask are not available from OHLCV parquet data.
            # These would require live market depth from the broker feed.
            bid=None,
            ask=None,
        )

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Return the last traded price for *symbol*.

        Reads only the final row via DuckDB ``ORDER BY ... LIMIT 1``
        instead of loading the entire parquet file.
        """
        symbol = normalize_symbol(symbol)
        candle = get_last_candle_fast(symbol, "1m", root=str(self._root))
        if candle is None:
            return Decimal("0")
        return Decimal(str(candle["close"]))

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        raise UnsupportedGatewayOperationError("DataLakeGateway", "depth")

    # -----------------------------------------------------------------------
    # MarketDataGateway — Batch
    # -----------------------------------------------------------------------

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get LTP for multiple symbols via batch DuckDB query.

        P2-4 fix: Uses DISTINCT ON instead of ROW_NUMBER() for better performance.
        DISTINCT ON avoids the full sort per symbol that ROW_NUMBER requires.
        """
        if not symbols:
            return {}

        normalized = [normalize_symbol(s) for s in symbols]
        placeholders = ",".join("?" for _ in normalized)

        # Try DuckDB with curated layout first
        try:
            curated_glob = curated_equity_glob(root=str(self._curated_root))
            query = f"""
                SELECT DISTINCT ON (symbol) symbol, close
                FROM read_parquet(?)
                WHERE symbol IN ({placeholders})
                ORDER BY symbol, timestamp DESC
            """
            df = duckdb.execute(query, [curated_glob, *normalized]).fetchdf()
            if not df.empty:
                return {
                    symbol: Decimal(str(close))
                    for symbol, close in zip(df["symbol"], df["close"], strict=False)
                    if pd.notna(symbol) and pd.notna(close)
                }
        except Exception as exc:
            logger.debug("Curated ltp_batch failed, trying legacy: %s", exc)

        # Try DuckDB with legacy layout
        try:
            parquet_paths = self._legacy_parquet_paths(symbols, "1m")
            if parquet_paths:
                source = parquet_paths[0] if len(parquet_paths) == 1 else parquet_paths
                query = f"""
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM read_parquet(?)
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, timestamp DESC
                """
                df = duckdb.execute(query, [source, *normalized]).fetchdf()
                if not df.empty:
                    return {
                        symbol: Decimal(str(close))
                        for symbol, close in zip(df["symbol"], df["close"], strict=False)
                        if pd.notna(symbol) and pd.notna(close)
                    }
        except Exception as exc:
            logger.debug("DuckDB ltp_batch failed, using fallback: %s", exc)

        # Fallback to sequential
        return {s: self.ltp(s, exchange) for s in symbols}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, dict]:
        """Return quotes for multiple symbols using parallel execution."""
        return self._batch_execute(lambda s: self.quote(s, exchange), symbols)

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Return historical data for multiple symbols via DuckDB batch query.

        P0-4 fix: Uses explicit column list instead of SELECT * for
        projection pushdown into parquet scan.
        """
        if not symbols:
            return pd.DataFrame()

        # Standard OHLCV columns to project
        columns = "timestamp, open, high, low, close, volume, oi, symbol"

        # Try curated layout first
        try:
            curated_glob = curated_equity_glob(root=str(self._curated_root))
            normalized = [normalize_symbol(s) for s in symbols]
            placeholders = ",".join("?" for _ in normalized)
            query = f"""
                SELECT {columns}
                FROM read_parquet(?)
                WHERE symbol IN ({placeholders})
            """
            df = duckdb.execute(query, [curated_glob, *normalized]).fetchdf()
            if not df.empty:
                df = self._filter_by_date(df, lookback_days=lookback_days)
                df["timeframe"] = timeframe
            return df
        except Exception as exc:
            logger.debug("Curated history_batch failed, trying legacy: %s", exc)

        # Build list of legacy parquet paths
        parquet_paths = self._legacy_parquet_paths(symbols, timeframe)
        if not parquet_paths:
            return pd.DataFrame()

        try:
            placeholders = ",".join("?" for _ in symbols)
            normalized = [normalize_symbol(s) for s in symbols]
            query = f"""
                SELECT {columns}
                FROM read_parquet(?)
                WHERE symbol IN ({placeholders})
            """

            df = duckdb.execute(query, [parquet_paths, *normalized]).fetchdf()

            if not df.empty:
                df = self._filter_by_date(df, lookback_days=lookback_days)
                df["timeframe"] = timeframe

            return df

        except Exception as exc:
            logger.warning("DuckDB batch query failed, falling back to sequential: %s", exc)
            return self._history_batch_sequential(symbols, exchange, timeframe, lookback_days)

    def _history_batch_sequential(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Fallback sequential batch read (original implementation)."""
        frames = [self.history(s, exchange, timeframe, lookback_days) for s in symbols]
        valid_frames = [f for f in frames if f is not None and not f.empty]
        if not valid_frames:
            return pd.DataFrame()
        return pd.concat(valid_frames, ignore_index=True)

    def _batch_execute(
        self,
        fn: callable,
        symbols: list[str],
        max_workers: int = BATCH_MAX_WORKERS,
    ) -> dict[str, Any]:
        from brokers.common.batch_executor import batch_execute

        return batch_execute(symbols, fn, max_workers=max_workers)

    # -----------------------------------------------------------------------
    # Instrument (narrow interface: InstrumentProvider)
    # -----------------------------------------------------------------------

    def search(self, query: str, exchange: str = "NSE") -> list[dict]:
        symbols = self.list_symbols()
        matches = [s for s in symbols if query.upper() in s.upper()]
        return [{"symbol": s, "exchange": exchange, "name": s} for s in matches[:20]]

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        return None

    # -----------------------------------------------------------------------
    # Lifecycle (narrow interface: LifecycleAware)
    # -----------------------------------------------------------------------

    def describe(self) -> dict:
        symbols = self.list_symbols()
        layout = self._store._layout_in_use()
        return {
            "name": "DataLakeGateway",
            "type": "parquet",
            "root": str(self._root),
            "curated_root": str(self._curated_root),
            "layout": layout,
            "symbols": len(symbols),
            "timeframes": ["1m"],
        }

    def capabilities(self) -> BrokerCapabilities:
        from brokers.common.capabilities import (
            BrokerCapabilities,
            HistoricalWindowConstraint,
        )

        return BrokerCapabilities(
            broker_id="datalake",
            supports_place_order=False,
            supports_cancel_order=False,
            supports_modify_order=False,
            supports_historical_data=True,
            supports_intraday_history=True,
            supports_expired_options_history=True,
            supports_live_market_data=False,
            supports_depth=False,
            supports_option_chain=False,
            supports_polling_fallback=False,
            supports_order_stream=False,
            supports_portfolio_stream=False,
            supports_news=False,
            supports_fundamentals=False,
            supports_super_order=False,
            supports_forever_order=False,
            supports_native_slice_order=False,
            historical_windows=(
                HistoricalWindowConstraint(
                    timeframe="1m",
                    max_lookback_days=365 * 6,
                    max_chunk_days=365,
                    supports_expired_instruments=True,
                ),
            ),
            latency_class="low",
            reliability_class="tier1",
            product_types=frozenset(),
            order_types=frozenset(),
        )

    def close(self) -> None:
        pass

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        from brokers.common.gateway_errors import UnsupportedGatewayOperationError
        raise UnsupportedGatewayOperationError("DataLakeGateway", "streaming")

    # -----------------------------------------------------------------------
    # DataLake-specific helpers
    # -----------------------------------------------------------------------

    def _legacy_parquet_paths(self, symbols: list[str], timeframe: str) -> list[str]:
        """Build list of existing legacy parquet paths for *symbols*."""
        timeframe_dir = self._candles_dir / f"timeframe={timeframe}"
        paths = []
        for symbol in symbols:
            path = timeframe_dir / f"symbol={normalize_symbol(symbol)}" / "data.parquet"
            if path.exists():
                paths.append(str(path))
        return paths

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        return self._store.list_symbols(timeframe)

    def load_candles_parallel(
        self,
        symbols: list[str],
        timeframe: str = "1m",
        max_workers: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Load candles for multiple symbols in parallel using a thread pool."""
        if max_workers is None:
            max_workers = self._download_pool_max_workers

        results: dict[str, pd.DataFrame] = {}

        def load_single(symbol: str):
            """Load candles for single symbol."""
            try:
                df = self._load_parquet(symbol, timeframe)
                return symbol, df, None
            except Exception as exc:
                return symbol, None, exc

        # Parallel load using thread pool
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {executor.submit(load_single, symbol): symbol for symbol in symbols}

            # Collect results as they complete
            for future in as_completed(futures):
                symbol, df, error = future.result()
                if error:
                    logger.warning("parallel_load_failed: symbol=%s error=%s", symbol, error)
                elif df is not None and not df.empty:
                    results[symbol] = df

        logger.info(
            "parallel_load_complete: requested=%d successful=%d", len(symbols), len(results)
        )

        return results
