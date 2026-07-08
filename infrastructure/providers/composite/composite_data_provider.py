"""CompositeDataProvider — delegates to multiple providers with fallback.

Tries each provider in order until one succeeds.  Useful for composing
broker data with CSV/cache fallback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from domain.entities.options import FutureChain, OptionChain
from domain.entities.market import MarketDepth
from domain.instrument_id import InstrumentId
from domain.providers.protocols import Subscription

logger = logging.getLogger(__name__)


class _NullSubscription:
    """No-op subscription when no provider can subscribe."""

    @property
    def is_active(self) -> bool:
        return False

    def unsubscribe(self) -> None:
        pass


class CompositeDataProvider:
    """DataProvider that delegates to multiple providers with fallback.

    Parameters
    ----------
    providers:
        Ordered list of DataProvider instances.  The first provider that
        returns a non-None/non-empty result wins.
    """

    def __init__(self, providers: list[Any]) -> None:
        if not providers:
            raise ValueError("CompositeDataProvider requires at least one provider")
        self._providers = list(providers)

    @property
    def name(self) -> str:
        names = [p.name for p in self._providers]
        return f"composite({'/'.join(names)})"

    def get_quote(self, instrument_id: InstrumentId) -> Any | None:
        for provider in self._providers:
            try:
                result = provider.get_quote(instrument_id)
                if result is not None:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for get_quote(%s): %s", provider.name, instrument_id, exc)
        return None

    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        for provider in self._providers:
            try:
                result = provider.get_history(
                    instrument_id,
                    timeframe=timeframe,
                    lookback_days=lookback_days,
                    from_date=from_date,
                    to_date=to_date,
                )
                if result is not None and not result.empty:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for get_history(%s): %s", provider.name, instrument_id, exc)
        return pd.DataFrame()

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        for provider in self._providers:
            try:
                result = provider.get_depth(instrument_id)
                if result is not None:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for get_depth(%s): %s", provider.name, instrument_id, exc)
        return None

    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        for provider in self._providers:
            try:
                result = provider.get_option_chain(underlying, expiry=expiry)
                if result and result.strikes:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for get_option_chain(%s): %s", provider.name, underlying, exc)
        return OptionChain(underlying=underlying.underlying, exchange=underlying.exchange, expiry="")

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        for provider in self._providers:
            try:
                result = provider.get_future_chain(underlying)
                if result and result.contracts:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for get_future_chain(%s): %s", provider.name, underlying, exc)
        return FutureChain(underlying=underlying.underlying, exchange=underlying.exchange)

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> Subscription:
        for provider in self._providers:
            try:
                result = provider.subscribe(instrument_id, callback, depth=depth)
                if result is not None:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for subscribe(%s): %s", provider.name, instrument_id, exc)
        return _NullSubscription()

    def unsubscribe(self, subscription: Subscription) -> None:
        subscription.unsubscribe()

    def history_batch(
        self,
        instrument_ids: list[InstrumentId],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
    ) -> pd.DataFrame:
        for provider in self._providers:
            try:
                result = provider.history_batch(
                    instrument_ids,
                    timeframe=timeframe,
                    lookback_days=lookback_days,
                )
                if result is not None and not result.empty:
                    return result
            except Exception as exc:
                logger.debug("Provider %s failed for history_batch: %s", provider.name, exc)
        return pd.DataFrame()

    def list_instruments(self, exchange: str | None = None) -> list[InstrumentId]:
        all_instruments: list[InstrumentId] = []
        seen: set[str] = set()
        for provider in self._providers:
            try:
                instruments = provider.list_instruments(exchange=exchange)
                for inst in instruments:
                    key = str(inst)
                    if key not in seen:
                        seen.add(key)
                        all_instruments.append(inst)
            except Exception as exc:
                logger.debug("Provider %s failed for list_instruments: %s", provider.name, exc)
        return all_instruments
