"""CsvDataProvider — DataProvider backed by CSV files.

Loads OHLCV data from CSV files.  Supports single-symbol and
multi-symbol CSVs.  Data is cached after first load.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from domain.constants import DEFAULT_EXCHANGE
from domain.entities.market import MarketDepth
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import SubscriptionHandle
from infrastructure.providers.null.stubs import NullSubscription

logger = logging.getLogger(__name__)


class _NullSubscription(NullSubscription):
    """Backward-compatible alias for CSV provider."""


class CsvDataProvider:
    """DataProvider backed by CSV files.

    Parameters
    ----------
    path:
        Path to a CSV file or directory of CSV files.
    symbol_column:
        Column name used to identify symbols in multi-symbol CSVs.
        Ignored for single-symbol files.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        symbol_column: str = "symbol",
        name: str = "csv",
    ) -> None:
        self._path = Path(path)
        self._symbol_column = symbol_column
        self._name = name
        self._cache: dict[str, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        return self._name

    def _load(self, symbol: str) -> pd.DataFrame:
        """Load and cache CSV data for a symbol."""
        key = symbol.upper()
        if key in self._cache:
            return self._cache[key]

        if self._path.is_file():
            df = pd.read_csv(self._path)
            if self._symbol_column in df.columns:
                self._cache[key] = df[df[self._symbol_column].str.upper() == key].copy()
            else:
                self._cache[key] = df
        elif self._path.is_dir():
            # Try common file naming patterns
            candidates = [
                self._path / f"{key}.csv",
                self._path / f"{key.lower()}.csv",
                self._path / f"{key}_1m.csv",
            ]
            for candidate in candidates:
                if candidate.exists():
                    self._cache[key] = pd.read_csv(candidate)
                    break
            else:
                self._cache[key] = pd.DataFrame()
        else:
            self._cache[key] = pd.DataFrame()

        return self._cache[key]

    def get_quote(self, instrument_id: InstrumentId) -> Any | None:
        """Get latest quote from CSV (last row)."""
        from decimal import Decimal

        df = self._load(instrument_id.underlying)
        if df.empty:
            return None
        from domain.entities.market import Quote

        last = df.iloc[-1]
        return Quote(
            symbol=instrument_id.underlying,
            ltp=Decimal(str(last.get("close", 0))),
            open=Decimal(str(last.get("open", 0))),
            high=Decimal(str(last.get("high", 0))),
            low=Decimal(str(last.get("low", 0))),
            close=Decimal(str(last.get("close", 0))),
            volume=int(last.get("volume", 0)),
        )

    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Load historical OHLCV from CSV."""
        df = self._load(instrument_id.underlying)
        if df.empty:
            return df

        df = df.copy()

        # Normalize timestamp column
        ts_candidates = ["timestamp", "date", "Date", "Timestamp", "time"]
        ts_col = next((c for c in ts_candidates if c in df.columns), None)
        if ts_col:
            df["timestamp"] = pd.to_datetime(df[ts_col])
            df = df.sort_values("timestamp")

            if from_date:
                df = df[df["timestamp"] >= pd.Timestamp(from_date)]
            if to_date:
                df = df[df["timestamp"] <= pd.Timestamp(to_date)]

            # NOTE: No lookback_days filter for CSV data.
            # CSV data is static and represents the complete dataset.
            # The caller can filter by from_date/to_date if needed.
        else:
            # No timestamp column — return as-is (static data)
            pass

        return df.reset_index(drop=True)

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        """CSV data does not include market depth."""
        return None

    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        """CSV data does not include option chains."""
        return OptionChain(
            underlying=underlying.underlying, exchange=underlying.exchange, expiry=""
        )

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        """CSV data does not include futures chains."""
        return FutureChain(underlying=underlying.underlying, exchange=underlying.exchange)

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        """CSV data does not support live subscriptions."""
        return _NullSubscription()

    def unsubscribe(self, subscription: SubscriptionHandle) -> None:
        """No-op for CSV data."""
        pass

    def history_batch(
        self,
        instrument_ids: list[InstrumentId],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
    ) -> pd.DataFrame:
        """Load historical OHLCV for multiple instruments from CSV."""
        frames = []
        for iid in instrument_ids:
            df = self.get_history(iid, timeframe=timeframe, lookback_days=lookback_days)
            if not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def list_instruments(self, exchange: str | None = None) -> list[InstrumentId]:
        """List instruments found in CSV files."""
        instruments = []
        if self._path.is_dir():
            for csv_file in self._path.glob("*.csv"):
                symbol = csv_file.stem.upper()
                try:
                    instruments.append(InstrumentId.equity(exchange or DEFAULT_EXCHANGE, symbol))
                except ValueError:
                    continue
        return instruments
