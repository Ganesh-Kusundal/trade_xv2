"""Broker-neutral market-data provider contracts for analytics.

V2: The ``MarketDataProvider`` protocol now bridges to the V2
``DataProvider`` protocol (which uses ``InstrumentId``).  Analytics
code that previously called ``provider.history("RELIANCE")`` continues
to work — the bridge translates ``str`` → ``InstrumentId`` internally.

New code should use ``Instrument`` as the entry point:

    instrument = registry.get_instrument(InstrumentId.equity("NSE", "RELIANCE"))
    df = instrument.get_history(timeframe="1D", lookback_days=120)
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from domain.entities import FutureChain, OptionChain
from domain.symbols import normalize_symbol


@runtime_checkable
class MarketDataProvider(Protocol):
    """Minimal interface required by analytics engines.

    Accepts both ``str`` symbols (backward compat) and ``InstrumentId``
    objects (V2).  Implementations should accept ``InstrumentId``
    internally and translate as needed.
    """

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame: ...

    def option_chain(self, underlying: str, *, expiry: str | None = None) -> OptionChain: ...

    def future_chain(self, underlying: str) -> FutureChain: ...

    def ltp(self, symbol: str, *, exchange: str = "NSE") -> float: ...


class DataFrameMarketDataProvider:
    def __init__(
        self,
        history: dict[str, pd.DataFrame],
        option_chains: dict[str, OptionChain | dict] | None = None,
        future_chains: dict[str, FutureChain | dict] | None = None,
        prices: dict[str, float] | None = None,
    ) -> None:
        self._history = history
        self.option_chains = option_chains or {}
        self.future_chains = future_chains or {}
        self.prices = prices or {}

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        del timeframe, lookback_days, from_date, to_date
        return self._history.get(normalize_symbol(symbol), pd.DataFrame())

    def option_chain(self, underlying: str, *, expiry: str | None = None) -> OptionChain:
        del expiry
        raw = self.option_chains.get(normalize_symbol(underlying))
        if isinstance(raw, OptionChain):
            return raw
        return OptionChain.from_dict(raw or {"strikes": []})

    def future_chain(self, underlying: str) -> FutureChain:
        raw = self.future_chains.get(normalize_symbol(underlying))
        if isinstance(raw, FutureChain):
            return raw
        return FutureChain.from_dict(raw or {"contracts": []})

    def ltp(self, symbol: str, *, exchange: str = "NSE") -> float:
        del exchange
        return float(self.prices.get(normalize_symbol(symbol), 0.0))


class CsvMarketDataProvider:
    def __init__(self, path: str | Path, *, symbol_column: str = "symbol") -> None:
        self._path = Path(path)
        self._symbol_column = symbol_column
        self._cache: dict[str, pd.DataFrame] = {}

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        del timeframe, lookback_days, from_date, to_date
        key = symbol.upper()
        if key not in self._cache:
            df = pd.read_csv(self._path)
            if self._symbol_column in df.columns:
                self._cache[key] = df[df[self._symbol_column].str.upper() == key].copy()
            else:
                self._cache[key] = df
        return self._cache[key]

    def option_chain(self, underlying: str, *, expiry: str | None = None) -> OptionChain:
        del underlying, expiry
        return OptionChain(underlying="", exchange="", expiry="")

    def future_chain(self, underlying: str) -> FutureChain:
        del underlying
        return FutureChain(underlying="", exchange="")

    def ltp(self, symbol: str, *, exchange: str = "NSE") -> float:
        del symbol, exchange
        return 0.0


class GatewayMarketDataProvider:
    def __init__(self, gateway: MarketDataProvider) -> None:
        self._gateway = gateway

    def history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        return self._gateway.history(
            symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )

    def option_chain(self, underlying: str, *, expiry: str | None = None) -> OptionChain:
        chain = self._gateway.option_chain(underlying, expiry=expiry)
        if isinstance(chain, OptionChain):
            return chain
        return OptionChain.from_dict(chain)

    def future_chain(self, underlying: str) -> FutureChain:
        chain = self._gateway.future_chain(underlying)
        if isinstance(chain, FutureChain):
            return chain
        return FutureChain.from_dict(chain if isinstance(chain, dict) else {})

    def ltp(self, symbol: str, *, exchange: str = "NSE") -> float:
        return float(self._gateway.ltp(symbol, exchange=exchange))
