"""Specialized instrument types (Equity, ETF, Spot, Currency, Index)."""

from __future__ import annotations

from typing import Any

from domain.instruments.instrument import Instrument
from domain.instruments.instrument_id import InstrumentId


class Equity(Instrument):
    """Equity instrument. ``Equity("RELIANCE")``."""

    def __init__(self, symbol: str, exchange: str = "NSE", **kwargs: Any) -> None:
        super().__init__(InstrumentId.equity(exchange, symbol), **kwargs)


class ETF(Equity):
    """Exchange-traded fund — cash-like with AssetKind.ETF."""

    def __init__(self, symbol: str, exchange: str = "NSE", **kwargs: Any) -> None:
        Instrument.__init__(self, InstrumentId.etf(exchange, symbol), **kwargs)


class Spot(Instrument):
    """Spot instrument (FX / commodity spot when provider supports it)."""

    def __init__(self, symbol: str, exchange: str = "NSE", **kwargs: Any) -> None:
        super().__init__(InstrumentId.spot(exchange, symbol), **kwargs)


class Currency(Instrument):
    """Currency pair / currency underlying (cash form)."""

    def __init__(self, symbol: str, exchange: str = "NSE", **kwargs: Any) -> None:
        super().__init__(InstrumentId.currency(exchange, symbol), **kwargs)


class Index(Instrument):
    """Index instrument. ``Index("NIFTY")``."""

    def __init__(self, name: str, exchange: str = "NSE", **kwargs: Any) -> None:
        super().__init__(InstrumentId.index(exchange, name), **kwargs)
