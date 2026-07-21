"""DataLakeGateway — MarketDataGateway implementation backed by Parquet lake.

Provides the same interface as Dhan/Upstox/Paper gateways, but reads
historical data from the local Parquet lake instead of a live broker.
Used for backtesting, research, and offline analysis.

This gateway is **storage/read-only**: it does not place orders, run
strategies, or own backtest engines. Wire it into analytics consumers
(e.g. analytics.backtest.BacktestEngine) from the analytics/CLI layer.

Usage:
    from datalake.gateway import DataLakeGateway

    gw = DataLakeGateway()
    df = gw.history("RELIANCE", timeframe="1D", lookback_days=365)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from datalake.core.symbols import (
    normalize_symbol_for_storage,
    symbol_to_path,
)
from domain import MarketDepth, Quote
from domain.capabilities.broker_capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
)
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway

logger = logging.getLogger(__name__)


class DataLakeGateway(MarketDataGateway):
    """MarketDataGateway backed by local Parquet data lake.

    Implements the read-only subset of the MarketDataGateway contract.
    Trading methods raise NotImplementedError.
    """

    def __init__(self, root: str | None = None) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS

            root = DEFAULT_DATA_PATHS.lake_root
        self._root = Path(root)
        # Prefer equities; indices consulted as fallback in _candle_candidates.
        self._candles_dir = self._root / "equities" / "candles"

    def _parquet_path(self, symbol: str, timeframe: str) -> Path:
        return (
            self._candles_dir / f"timeframe={timeframe}" / symbol_to_path(symbol) / "data.parquet"
        )

    def _candle_candidates(self, symbol: str, timeframe: str) -> list[Path]:
        """Equity then index hive paths under the lake root."""
        leaf = Path(f"timeframe={timeframe}") / symbol_to_path(symbol) / "data.parquet"
        return [
            self._root / "equities" / "candles" / leaf,
            self._root / "indices" / "candles" / leaf,
        ]

    def _load_parquet(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        symbol = normalize_symbol_for_storage(symbol)
        for path in self._candle_candidates(symbol, timeframe):
            if not path.exists():
                continue
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
        """Resample 1m data to larger timeframe."""
        if df.empty:
            return df

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

        resampled = (
            df.resample(rule)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "oi": "last",
                }
            )
            .dropna()
        )

        resampled = resampled.reset_index()
        resampled["symbol"] = df["symbol"].iloc[0] if "symbol" in df.columns else ""
        resampled["exchange"] = df["exchange"].iloc[0] if "exchange" in df.columns else "NSE"
        resampled["timeframe"] = timeframe
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

        symbol = normalize_symbol_for_storage(symbol)
        df = self._load_parquet(symbol, timeframe)
        if df is None or df.empty:
            return pd.DataFrame()

        df = self._filter_by_date(df, from_date, to_date, lookback_days)
        if not df.empty:
            df["exchange"] = exchange
            df["timeframe"] = timeframe
        return df

    def query_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        from_ts: pd.Timestamp | None = None,
        to_ts: pd.Timestamp | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame | None:
        """Filter lake OHLCV for API routes (storage read; domain ingress follows)."""
        symbol = normalize_symbol_for_storage(symbol)
        df = self._load_parquet(symbol, timeframe)
        if df is None or df.empty:
            return None
        ts = pd.to_datetime(df["timestamp"])
        if from_ts is not None:
            df = df.loc[ts >= from_ts].copy()
            ts = pd.to_datetime(df["timestamp"])
        if to_ts is not None:
            df = df.loc[ts <= to_ts].copy()
        if limit is not None and limit > 0:
            df = df.tail(limit)
        return df.reset_index(drop=True)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        from domain import Quote as _Quote

        symbol = normalize_symbol_for_storage(symbol)
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
            bid=Decimal(str(last["low"])),
            ask=Decimal(str(last["high"])),
        )

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        symbol = normalize_symbol_for_storage(symbol)
        df = self._load_parquet(symbol, "1m")
        if df is None or df.empty:
            return Decimal("0")
        return Decimal(str(df.iloc[-1]["close"]))

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        from domain import MarketDepth as _MarketDepth

        return _MarketDepth(symbol=symbol)

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NSE",
        expiry: str | None = None,
    ) -> dict:
        """Load option chain from lake parquet when present (TOS-P6-002).

        Looks under ``{root}/options/chains/expiry=*/underlying={u}/data.parquet``.
        Returns empty calls/puts when no files exist (not a hard failure).
        """

        underlying = normalize_symbol_for_storage(underlying)
        root = self._root
        chains_root = root / "options" / "chains"
        calls: list[dict] = []
        puts: list[dict] = []
        resolved_expiry = expiry
        try:
            if chains_root.exists():
                pattern = (
                    f"expiry={expiry}/underlying={underlying}/data.parquet"
                    if expiry
                    else f"expiry=*/underlying={underlying}/data.parquet"
                )
                files = sorted(chains_root.glob(pattern))
                if files and expiry is None:
                    # Prefer latest expiry directory name.
                    resolved_expiry = files[-1].parts[-3].split("=", 1)[-1]
                for path in files[-3:]:  # cap reads
                    try:
                        import pandas as pd

                        df = pd.read_parquet(path)
                        if df is None or df.empty:
                            continue
                        side_col = "option_type" if "option_type" in df.columns else "type"
                        for _, row in df.iterrows():
                            rec = {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
                            ot = str(rec.get(side_col, "")).upper()
                            if ot in ("CE", "CALL", "C"):
                                calls.append(rec)
                            elif ot in ("PE", "PUT", "P"):
                                puts.append(rec)
                            else:
                                calls.append(rec)
                    except Exception:
                        continue
        except Exception:
            pass
        return {
            "underlying": underlying,
            "exchange": exchange,
            "calls": calls,
            "puts": puts,
            "expiry": resolved_expiry,
        }

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> list[dict]:
        """Load futures chain from lake when present (TOS-P6-002)."""

        underlying = normalize_symbol_for_storage(underlying)
        root = self._root
        fut_root = root / "futures" / "chains"
        out: list[dict] = []
        try:
            if fut_root.exists():
                import pandas as pd

                for path in sorted(fut_root.glob(f"underlying={underlying}/**/data.parquet")):
                    try:
                        df = pd.read_parquet(path)
                        if df is None or df.empty:
                            continue
                        for _, row in df.iterrows():
                            out.append(
                                {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
                            )
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    def stream(self, symbols: list[str], exchange: str = "NSE") -> Any:
        from domain.errors import UnsupportedGatewayOperationError

        raise UnsupportedGatewayOperationError("DataLakeGateway", "streaming")

    # -----------------------------------------------------------------------
    # MarketDataGateway — Batch
    #
    # REF-32: previous versions of these methods did a serial ``for sym in
    # symbols: self.<single>(sym)`` loop. Each call did a separate
    # ``pd.read_parquet`` of a single file. For 100 symbols this was 100
    # sequential file opens — an N+1 IO pattern that did not scale beyond
    # ~50 symbols.
    #
    # The implementation below uses ``ThreadPoolExecutor`` to read
    # multiple Parquet files in parallel. The default worker count is
    # the same as :class:`brokers.common.batch_mixin.BatchFetchMixin`
    # so the two paths behave consistently.
    # -----------------------------------------------------------------------

    _batch_max_workers: int = 5

    def _batch_execute(
        self,
        fn,
        symbols: list[str],
        drop_empty: bool = False,
    ) -> dict[str, Any]:
        """Run ``fn(symbol)`` for each symbol in parallel.

        Failures are swallowed and the symbol is omitted from the
        returned dict. This matches the contract of
        :class:`BatchFetchMixin` (best-effort partial results).

        ``drop_empty=True`` additionally drops any returned value
        that is an empty :class:`pandas.DataFrame`. Use this for
        ``history_batch`` so callers don't have to filter ``None``
        or empty frames out of the dict post-hoc.
        """
        results: dict[str, Any] = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=self._batch_max_workers) as executor:
            futures = {executor.submit(fn, s): s for s in symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    value = future.result()
                except Exception as exc:
                    logger.debug("datalake_batch_fetch_failed: %s: %s", sym, exc)
                    continue
                if drop_empty and isinstance(value, pd.DataFrame) and value.empty:
                    continue
                results[sym] = value
        return results

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return self._batch_execute(lambda s: self.ltp(s, exchange), symbols)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, dict]:
        return self._batch_execute(lambda s: self.quote(s, exchange), symbols)

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> dict[str, pd.DataFrame]:
        return self._batch_execute(
            lambda s: self.history(s, exchange, timeframe, lookback_days),
            symbols,
            drop_empty=True,
        )

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

    def funds(self) -> dict:
        raise NotImplementedError("DataLakeGateway does not support portfolio")

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
            broker_id="datalake",
            supports_place_order=False,
            supports_cancel_order=False,
            supports_modify_order=False,
            supports_historical_data=True,
            supports_intraday_history=True,
            supports_expired_options_history=True,
            supports_live_market_data=False,
            supports_depth=False,
            supports_depth_20_ws=False,
            supports_depth_200_ws=False,
            supports_option_chain=False,
            supports_polling_fallback=False,
            supports_order_stream=False,
            supports_portfolio_stream=False,
            supports_news=False,
            supports_fundamentals=False,
            supports_super_order=False,
            supports_forever_order=False,
            supports_native_slice_order=False,
            rate_limit_profiles=(),
            historical_windows=(
                HistoricalWindowConstraint(
                    timeframe="1m", max_lookback_days=365 * 6, max_chunk_days=365
                ),
                HistoricalWindowConstraint(
                    timeframe="1d", max_lookback_days=365 * 10, max_chunk_days=365
                ),
            ),
            stream_limits=None,
            latency_class="low",
            reliability_class="high",
            product_types=frozenset(),
            order_types=frozenset(),
            max_batch_size=50,
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
