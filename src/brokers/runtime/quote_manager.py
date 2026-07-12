"""QuoteManager — coordinates quote/depth refresh for instruments.

Thin coordinator over ``Instrument.refresh`` / ``Instrument.depth``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.entities.market import MarketDepth, QuoteSnapshot
    from domain.instruments.instrument import Instrument


class QuoteManager:
    """Coordinates quote + market-depth retrieval for instruments."""

    def quote(self, instrument: Instrument) -> QuoteSnapshot | None:
        return instrument.refresh()

    def depth(self, instrument: Instrument) -> MarketDepth | None:
        return instrument.depth()

    def statistics(self, instrument: Instrument) -> dict[str, Any]:
        return instrument.statistics()