"""DataLakeGateway — MarketDataGateway implementation backed by Parquet lake.

Provides the same interface as Dhan/Upstox/Paper gateways, but reads
historical data from the local Parquet lake instead of a live broker.
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

import duckdb
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from cachetools import TTLCache

from brokers.common.core.domain import Balance, MarketDepth, Quote
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway
from datalake.symbols import normalize_symbol, symbol_to_path
from datalake.cache_utils import generate_cache_key, load_candles_projected

logger = logging.getLogger(__name__)


class DataLakeGateway(MarketDataGateway):
    """MarketDataGateway backed by local Parquet data lake.

    Implements the read-only subset of the MarketDataGateway contract.
    Trading methods raise NotImplementedError.
    """

    def __init__(self, root: str = "market_data") -> None:
        self._root = Path(root)
        self._candles_dir = self._root / "equities" / "candles"
        # I-18: resample cache keyed by (symbol, timeframe) with TTL and memory bounds
        # Using cachetools.TTLCache with:
        # - maxsize=100 entries
        # - ttl=300 seconds (5 minutes)
        # - getsizeof to track memory usage
        self._resample_cache: TTLCache = TTLCache(
            maxsize=100,
            ttl=300,
            getsizeof=self._df_size,
        )
        self._resample_cache_lock = threading.Lock()
        # Thread pool for parallel downloads
        self._download_pool_max_workers = 4

    @staticmethod
    def _df_size(df: pd.DataFrame) -> int:
        """Calculate memory size of a DataFrame in bytes."""
        return int(df.memory_usage(deep=True).sum())

    def _parquet_path(self, symbol: str, timeframe: str) -> Path:
        return self._candles_dir / f"timeframe={timeframe}" / symbol_to_path(symbol) / "data.parquet"

    def _load_parquet(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        symbol = normalize_symbol(symbol)
        path = self._parquet_path(symbol, timeframe)
        if path.exists():
            try:
                return pd.read_parquet(path)
            except Exception as exc:
                logger.error("Failed to read %s: %s", path, exc)
                return None

        if timeframe != "1m":
            df_1m = self._load_parquet(symbol, "1m")
            if df_1m is not None and not df_1m.empty:
                return self._resample(df_1m, timeframe)

        logger.warning("No data for %s/%s", symbol, timeframe)
        return None

    def _resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Resample 1m data to larger timeframe (with TTL-bounded cache)."""
        if df.empty:
            return df

        # Check cache — keyed by symbol + timeframe
        symbol = df["symbol"].iloc[0] if "symbol" in df.columns else ""
        cache_key = generate_cache_key(symbol, timeframe)
        
        with self._resample_cache_lock:
            if cache_key in self._resample_cache:
                # Return cached copy — defensive copy to prevent mutation
                return self._resample_cache[cache_key].copy()

        # Work on a copy only once
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")

        # Map timeframe to pandas rule
        rule_map = {
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
            "1D": "1D",
        }
        rule = rule_map.get(timeframe)
        if not rule:
            return df.reset_index()

        resampled = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "oi": "last",
        }).dropna()

        resampled = resampled.reset_index()
        resampled["symbol"] = df["symbol"].iloc[0] if "symbol" in df.columns else ""
        resampled["exchange"] = df["exchange"].iloc[0] if "exchange" in df.columns else "NSE"
        resampled["timeframe"] = timeframe

        # Cache the result with TTL and memory bounds
        with self._resample_cache_lock:
            self._resample_cache[cache_key] = resampled
        
        return resampled

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
        return df

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get latest quote snapshot for a symbol from OHLCV parquet data.

        Returns a Quote with OHLCV fields populated from the most recent 1-minute
        candle. Bid/ask are always None because order book depth is not available
        from historical OHLCV parquet files — only live broker market feeds provide
        bid/ask quotations.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "TCS").
            exchange: Exchange name (default: "NSE").

        Returns:
            Quote with ltp, open, high, low, close, volume, change populated.
            bid and ask are always None for historical data.

        Note:
            bid/ask require live market depth (Level 2 data) from broker WebSocket
            feeds. OHLCV parquet files only contain aggregated candle data, not
            the order book snapshots needed to derive bid/ask prices.
        """
        from brokers.common.core.domain import Quote as _Quote
        symbol = normalize_symbol(symbol)
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
        symbol = normalize_symbol(symbol)
        df = self._load_parquet(symbol, "1m")
        if df is None or df.empty:
            return Decimal("0")
        return Decimal(str(df.iloc[-1]["close"]))

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        from brokers.common.core.domain import MarketDepth as _MarketDepth
        return _MarketDepth(symbol=symbol)

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NSE",
        expiry: str | None = None,
    ) -> dict:
        return {"underlying": underlying, "calls": [], "puts": [], "expiry": expiry}

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> list[dict]:
        return []

    def stream(self, symbols: list[str], exchange: str = "NSE") -> Any:
        raise NotImplementedError("DataLakeGateway does not support live streaming")

    # -----------------------------------------------------------------------
    # MarketDataGateway — Batch
    # -----------------------------------------------------------------------

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get LTP for multiple symbols using batch parquet read.

        Uses DuckDB to read the last row of each symbol's parquet file in a
        single query, avoiding sequential pd.read_parquet() calls.

        Performance: 500 symbols in <2 seconds (vs 5-10 seconds sequential).

        Falls back to sequential read if DuckDB query fails.
        """
        if not symbols:
            return {}

        # Try DuckDB for batch read
        try:
            timeframe_dir = self._candles_dir / "timeframe=1m"
            parquet_paths = []
            for symbol in symbols:
                symbol = normalize_symbol(symbol)
                path = timeframe_dir / f"symbol={symbol}" / "data.parquet"
                if path.exists():
                    parquet_paths.append(str(path))

            if parquet_paths:
                # Read last row of each file using window function
                # Parameterized DuckDB query — DuckDB accepts Python lists as bound parameters
                query = """
                    SELECT symbol, close
                    FROM (
                        SELECT symbol, close,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
                        FROM read_parquet(?)
                    )
                    WHERE rn = 1
                """
                df = duckdb.execute(query, [parquet_paths]).fetchdf()
                return {row["symbol"]: Decimal(str(row["close"])) for _, row in df.iterrows()}
        except Exception as exc:
            logger.debug("DuckDB ltp_batch failed, using fallback: %s", exc)

        # Fallback to sequential
        return {s: self.ltp(s, exchange) for s in symbols}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, dict]:
        """Return quotes for multiple symbols using parallel execution.

        Uses ThreadPoolExecutor to fetch quotes concurrently, with
        exception isolation per symbol.

        Performance: 4 symbols with 100ms each completes in ~100ms
        (vs 400ms sequential).
        """
        return self._batch_execute(lambda s: self.quote(s, exchange), symbols)

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Return historical data for multiple symbols using DuckDB glob query.

        Uses DuckDB's read_parquet with list of paths to read all symbol files
        in a single query, avoiding sequential pd.read_parquet() calls.

        Performance: 500 symbols in <2 seconds (vs 5-10 seconds sequential).

        Falls back to sequential read if DuckDB query fails.
        """
        if not symbols:
            return pd.DataFrame()

        # Build list of parquet paths for all requested symbols
        timeframe_dir = self._candles_dir / f"timeframe={timeframe}"
        if not timeframe_dir.exists():
            return pd.DataFrame()

        parquet_paths = []
        for symbol in symbols:
            symbol = normalize_symbol(symbol)
            path = timeframe_dir / f"symbol={symbol}" / "data.parquet"
            if path.exists():
                parquet_paths.append(str(path))

        if not parquet_paths:
            return pd.DataFrame()

        # Use DuckDB to read all files in one query
        try:
            query = """
                SELECT *
                FROM read_parquet(?)
            """

            df = duckdb.execute(query, [parquet_paths]).fetchdf()

            # Filter by date range
            if not df.empty:
                df = self._filter_by_date(df, lookback_days=lookback_days)
                df["timeframe"] = timeframe

            return df

        except Exception as exc:
            logger.warning("DuckDB batch query failed, falling back to sequential: %s", exc)
            # Fallback to sequential read
            return self._history_batch_sequential(symbols, exchange, timeframe, lookback_days)

    def _history_batch_sequential(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """Fallback sequential batch read (original implementation)."""
        frames = [
            self.history(s, exchange, timeframe, lookback_days)
            for s in symbols
        ]
        valid_frames = [f for f in frames if f is not None and not f.empty]
        if not valid_frames:
            return pd.DataFrame()
        return pd.concat(valid_frames, ignore_index=True)

    def _batch_execute(
        self,
        fn: callable,
        symbols: list[str],
        max_workers: int = 5,
    ) -> dict[str, Any]:
        """Execute fn(symbol) for each symbol in parallel.

        Uses ThreadPoolExecutor for I/O-bound work. Exceptions per symbol
        are logged and that symbol is omitted from results.

        Args:
            fn: Callable that takes a symbol string and returns any value.
            symbols: List of symbol strings.
            max_workers: Maximum number of concurrent threads.

        Returns:
            Dict mapping symbol -> result for successful executions.
        """
        if not symbols:
            return {}

        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(fn, s): s for s in symbols
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    results[symbol] = future.result()
                except Exception as exc:
                    logger.debug("batch_execute failed for %s: %s", symbol, exc)
        return results

    # -----------------------------------------------------------------------
    # MarketDataGateway — Trading (not supported)
    # -----------------------------------------------------------------------

    def place_order(self, *args, **kwargs) -> Any:
        raise NotImplementedError("DataLakeGateway does not support trading")

    def cancel_order(self, *args, **kwargs) -> bool:
        raise NotImplementedError("DataLakeGateway does not support trading")

    def get_orderbook(self) -> list[Any]:
        raise NotImplementedError("DataLakeGateway does not support trading")

    def get_trade_book(self) -> list[Any]:
        raise NotImplementedError("DataLakeGateway does not support trading")

    # -----------------------------------------------------------------------
    # MarketDataGateway — Portfolio (not supported)
    # -----------------------------------------------------------------------

    def positions(self) -> list[Any]:
        raise NotImplementedError("DataLakeGateway does not support portfolio")

    def holdings(self) -> list[Any]:
        raise NotImplementedError("DataLakeGateway does not support portfolio")

    def funds(self) -> Balance:
        """Return fund limits.

        DataLakeGateway does not support portfolio operations.
        Returns a Balance with zero values per ABC contract.
        """
        return Balance(
            available_balance=Decimal("0"),
            used_margin=Decimal("0"),
            total_balance=Decimal("0"),
        )

    def trades(self) -> list[Any]:
        raise NotImplementedError("DataLakeGateway does not support portfolio")

    # -----------------------------------------------------------------------
    # MarketDataGateway — Instrument
    # -----------------------------------------------------------------------

    def search(self, query: str, exchange: str = "NSE") -> list[dict]:
        symbols = self.list_symbols()
        matches = [s for s in symbols if query.upper() in s.upper()]
        return [{"symbol": s, "exchange": exchange, "name": s} for s in matches[:20]]

    def load_instruments(self) -> Any:
        return None

    # -----------------------------------------------------------------------
    # MarketDataGateway — Lifecycle
    # -----------------------------------------------------------------------

    def describe(self) -> dict:
        symbols = self.list_symbols()
        return {
            "name": "DataLakeGateway",
            "type": "parquet",
            "root": str(self._root),
            "symbols": len(symbols),
            "timeframes": ["1m"],
        }

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            expired_options=True,
            expired_futures=True,
            max_intraday_days=365 * 6,
            max_daily_days=365 * 10,
            supported_timeframes=("1m",),
            websocket=False,
            polling_fallback=False,
            load_instruments=False,
            search=True,
        )

    def close(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # DataLake-specific helpers
    # -----------------------------------------------------------------------

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        tf_dir = self._candles_dir / f"timeframe={timeframe}"
        if not tf_dir.exists():
            return []
        return sorted(
            p.name.replace("symbol=", "")
            for p in tf_dir.iterdir()
            if p.is_dir() and p.name.startswith("symbol=")
        )
    
    def load_candles_parallel(
        self,
        symbols: list[str],
        timeframe: str = "1m",
        max_workers: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Load candles for multiple symbols in parallel.
        
        Uses thread pool to load historical data concurrently from
        parquet files. Ideal for backtesting multiple symbols or
        loading universe data.
        
        Performance: 3-5x faster than sequential loads for I/O-bound
        parquet reads, especially on SSD/NVMe storage.
        
        Args:
            symbols: List of instrument symbols
            timeframe: Candle timeframe (default: "1m")
            max_workers: Maximum parallel threads (default: 4)
            
        Returns:
            Dict mapping symbol -> DataFrame (only successful loads)
            
        Example:
            >>> gw = DataLakeGateway()
            >>> data = gw.load_candles_parallel(
            ...     ["RELIANCE", "TCS", "INFY"],
            ...     timeframe="1m"
            ... )
            >>> len(data)  # Number of successful loads
            3
        """
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
            futures = {
                executor.submit(load_single, symbol): symbol
                for symbol in symbols
            }
            
            # Collect results as they complete
            for future in as_completed(futures):
                symbol, df, error = future.result()
                if error:
                    logger.warning(
                        "parallel_load_failed: symbol=%s error=%s",
                        symbol,
                        error
                    )
                elif df is not None and not df.empty:
                    results[symbol] = df
        
        logger.info(
            "parallel_load_complete: requested=%d successful=%d",
            len(symbols),
            len(results)
        )
        
        return results
