"""DataLakeGateway — MarketDataGateway implementation backed by Parquet lake.

Provides the same interface as Dhan/Upstox/Paper gateways, but reads
historical data from the local Parquet lake instead of a live broker.
Used for backtesting, research, and offline analysis.

This gateway is **storage/read-only**: it does not place orders, run
strategies, or own backtest engines. Wire it into analytics consumers
(e.g. analytics.backtest.BacktestEngine) from the analytics/CLI layer.

Usage:
    from datalake.gateway import DataLakeGateway

    gw = DataLakeGateway(root="market_data")
    df = gw.history("RELIANCE", timeframe="1D", lookback_days=365)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from domain import MarketDepth, Quote
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from tradex.runtime.capabilities import BrokerCapabilities
from datalake.core.symbols import normalize_symbol, symbol_to_path

logger = logging.getLogger(__name__)


class DataLakeGateway(MarketDataGateway):
    """MarketDataGateway backed by local Parquet data lake.

    Implements the read-only subset of the MarketDataGateway contract.
    Trading methods raise NotImplementedError.
    """

    def __init__(self, root: str = "market_data") -> None:
        self._root = Path(root)
        self._candles_dir = self._root / "equities" / "candles"

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
        from domain import Quote as _Quote
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
            bid=Decimal(str(last["low"])),
            ask=Decimal(str(last["high"])),
        )

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        symbol = normalize_symbol(symbol)
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
