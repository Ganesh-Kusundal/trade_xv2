"""DataFrameDataProvider — in-memory DataFrames for testing.

Provides a DataProvider backed by pre-loaded DataFrames.  Primary use
case is unit and integration tests where you want deterministic data
without file I/O.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from domain.entities.options import FutureChain, OptionChain
from domain.entities.market import MarketDepth, Quote
from domain.instrument_id import InstrumentId
from domain.providers.protocols import Subscription

logger = logging.getLogger(__name__)


class _NullSubscription:
    """No-op subscription for in-memory data."""

    @property
    def is_active(self) -> bool:
        return False

    def unsubscribe(self) -> None:
        pass


class DataFrameDataProvider:
    """DataProvider backed by in-memory DataFrames.

    Parameters
    ----------
    history:
        Mapping of symbol (uppercase) → DataFrame with OHLCV columns.
    quotes:
        Mapping of symbol (uppercase) → Quote object.
    option_chains:
        Mapping of underlying symbol → OptionChain.
    future_chains:
        Mapping of underlying symbol → FutureChain.
    """

    def __init__(
        self,
        history: dict[str, pd.DataFrame] | None = None,
        quotes: dict[str, Quote] | None = None,
        option_chains: dict[str, OptionChain] | None = None,
        future_chains: dict[str, FutureChain] | None = None,
    ) -> None:
        self._history = {k.upper(): v for k, v in (history or {}).items()}
        self._quotes = {k.upper(): v for k, v in (quotes or {}).items()}
        self._option_chains = {k.upper(): v for k, v in (option_chains or {}).items()}
        self._future_chains = {k.upper(): v for k, v in (future_chains or {}).items()}

    @property
    def name(self) -> str:
        return "dataframe"

    def get_quote(self, instrument_id: InstrumentId) -> Quote | None:
        return self._quotes.get(instrument_id.underlying.upper())

    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        key = instrument_id.underlying.upper()
        df = self._history.get(key, pd.DataFrame())
        if df.empty:
            return df

        # Apply date filters if timestamp column exists
        if "timestamp" in df.columns and (from_date or to_date):
            df = df.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            if from_date:
                df = df[df["timestamp"] >= pd.Timestamp(from_date)]
            if to_date:
                df = df[df["timestamp"] <= pd.Timestamp(to_date)]

        return df

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        return None

    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        key = underlying.underlying.upper()
        chain = self._option_chains.get(key)
        if chain is not None:
            return chain
        return OptionChain(underlying=underlying.underlying, exchange=underlying.exchange, expiry="")

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        key = underlying.underlying.upper()
        chain = self._future_chains.get(key)
        if chain is not None:
            return chain
        return FutureChain(underlying=underlying.underlying, exchange=underlying.exchange)

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> Subscription:
        return _NullSubscription()

    def unsubscribe(self, subscription: Subscription) -> None:
        pass

    def history_batch(
        self,
        instrument_ids: list[InstrumentId],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
    ) -> pd.DataFrame:
        frames = []
        for iid in instrument_ids:
            df = self.get_history(iid, timeframe=timeframe, lookback_days=lookback_days)
            if not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def list_instruments(self, exchange: str | None = None) -> list[InstrumentId]:
        instruments = []
        for symbol in self._history:
            try:
                instruments.append(InstrumentId.equity(exchange or "NSE", symbol))
            except ValueError:
                continue
        return instruments
