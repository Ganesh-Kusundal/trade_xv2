"""Market data port for feature fetchers and orchestrators."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class MarketDataPort(Protocol):
    """Read-only historical market data (gateway or datalake backed)."""

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> pd.DataFrame | None: ...


class GatewayMarketDataAdapter:
    """Wraps a broker gateway ``history`` method as :class:`MarketDataPort`."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> pd.DataFrame | None:
        history_fn = getattr(self._gateway, "history", None)
        if history_fn is None:
            return None
        return history_fn(symbol, start, end, interval=interval, exchange=exchange)


class DataFrameMarketDataAdapter:
    """Serves pre-loaded OHLCV for replay/backtest parity tests."""

    def __init__(self, frames: dict[tuple[str, str], pd.DataFrame]) -> None:
        self._frames = frames

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> pd.DataFrame | None:
        key = (symbol.upper(), exchange.upper())
        df = self._frames.get(key)
        if df is None:
            return None
        if "date" in df.columns:
            mask = (df["date"] >= start) & (df["date"] <= end)
            return df.loc[mask].copy()
        return df.copy()
