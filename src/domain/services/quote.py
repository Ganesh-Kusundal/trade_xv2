"""QuoteService — live quote + depth access with an optional staleness cache.

Wraps a :class:`~domain.ports.protocols.DataProvider` so the ``Instrument``
never talks to a provider directly for quote/depth data.  Pure domain layer:
no broker or transport imports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.entities.market import MarketDepth, QuoteSnapshot
    from domain.instruments.instrument_id import InstrumentId
    from domain.ports.protocols import DataProvider


class QuoteService:
    """Quote/depth access with lightweight caching + metrics."""

    def __init__(self, provider: DataProvider | None) -> None:
        self._provider = provider
        self._quote_cache: QuoteSnapshot | None = None
        self._quote_at: datetime | None = None
        self._depth_cache: MarketDepth | None = None
        self._metrics: dict[str, int] = {"quotes": 0, "depths": 0}

    @property
    def provider(self) -> DataProvider | None:
        return self._provider

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        if self._provider is None:
            return None
        self._metrics["quotes"] += 1
        quote = self._provider.get_quote(instrument_id)
        if quote is not None:
            self._quote_cache = quote
            self._quote_at = datetime.now(tz=timezone.utc)
        return quote

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        if self._provider is None:
            return None
        self._metrics["depths"] += 1
        depth = self._provider.get_depth(instrument_id)
        if depth is not None:
            self._depth_cache = depth
        return depth

    @property
    def last_quote(self) -> QuoteSnapshot | None:
        return self._quote_cache

    def clear_cache(self) -> None:
        self._quote_cache = None
        self._depth_cache = None
        self._quote_at = None
