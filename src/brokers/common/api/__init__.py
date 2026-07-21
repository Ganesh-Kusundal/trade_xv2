from __future__ import annotations

"""Broker API contracts and SPI definitions.

ponytail: deprecated — prefer ``domain.ports.protocols`` (DataProvider / ExecutionProvider).
This SPI module remains for legacy margin/market-data provider aliases until callers migrate.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import pandas as pd

from brokers.common.api.spi import BrokerSource
from domain import (
    FundLimits,
    Holding,
    MarketDepth,
    OptionContract,
    Position,
    Quote,
)
from domain.market_enums import ExchangeId
from domain.exceptions import TradeXV2Error


class MarginProvider(Protocol):
    """Protocol for margin calculation."""

    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class MarginCalculationError(TradeXV2Error):
    """Raised when margin calculation fails."""


@dataclass(frozen=True)
class MarginResult:
    """Result of a margin calculation."""

    required_margin: Decimal
    available_margin: Decimal
    span_margin: Decimal | None = None
    exposure_margin: Decimal | None = None

    @property
    def is_sufficient(self) -> bool:
        """Check if available margin covers required margin."""
        return self.available_margin >= self.required_margin


class MarketDataProvider(Protocol):
    """Protocol for market data operations."""

    def quote(self, symbol: str, exchange: str = ExchangeId.NSE) -> Quote: ...

    def ltp(self, symbol: str, exchange: str = ExchangeId.NSE) -> Decimal: ...

    def depth(self, symbol: str, exchange: str = ExchangeId.NSE) -> MarketDepth: ...

    def history(
        self,
        symbol: str | list[str],
        exchange: str = ExchangeId.NSE,
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame: ...


class MarketStatusProvider(Protocol):
    """Protocol for market status operations."""

    def get_market_status(self) -> dict[str, Any]: ...


class OptionsProvider(Protocol):
    """Protocol for options chain operations."""

    def get_expiries(self, underlying: str, exchange_segment: str) -> list[str]: ...

    def get_option_chain(
        self, underlying: str, exchange_segment: str, expiry: str
    ) -> list[OptionContract]: ...

    def get_option_chain_with_meta(
        self, underlying: str, exchange_segment: str, expiry: str
    ) -> tuple[list[OptionContract], list[dict], dict]: ...


class PortfolioProvider(Protocol):
    """Protocol for portfolio operations."""

    def get_balance(self) -> Any: ...

    def get_positions(self) -> list[Position]: ...

    def get_holdings(self) -> list[Holding]: ...

    def get_fund_limits(self) -> FundLimits: ...

    def get_profile(self) -> dict[str, Any]: ...

    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]: ...


__all__ = [
    "BrokerSource",
    "MarginCalculationError",
    "MarginProvider",
    "MarginResult",
    "MarketDataProvider",
    "MarketStatusProvider",
    "OptionsProvider",
    "PortfolioProvider",
]
