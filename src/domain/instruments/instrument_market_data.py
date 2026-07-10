"""InstrumentMarketDataMixin — market-data query & snapshot methods.

Extracted from the Instrument god class (KD-202).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.value_objects.state import InstrumentState

if TYPE_CHECKING:
    import threading
    from domain.instruments.instrument_id import InstrumentId
    from domain.instruments.composition import InstrumentIdentity, TradingSpec
    from domain.ports.protocols import DataProvider

logger = logging.getLogger(__name__)


class InstrumentMarketDataMixin:
    """Mixin providing market-data query, refresh and snapshot methods for Instrument.

    Expects these attributes on ``self`` (provided by ``Instrument.__init__``):

        _provider, _lock, _state, _id, _identity, _trading, symbol,
        exchange, asset_type, lot_size, tick_size, _resolve_provider()
    """

    # ── Attribute declarations (provided by concrete class) ────────────

    _lock: threading.RLock
    _state: InstrumentState
    _id: InstrumentId
    _identity: InstrumentIdentity
    _trading: TradingSpec
    symbol: str
    exchange: str
    asset_type: str
    lot_size: int
    tick_size: Decimal | Any

    def _resolve_provider(self) -> DataProvider:  # pragma: no cover
        ...

    # ── Live State Accessors ──────────────────────────────────────────

    @property
    def quote(self) -> QuoteSnapshot | None:
        return self._state.quote

    @property
    def ltp(self) -> Decimal | None:
        q = self._state.quote
        return q.ltp if q else None

    @property
    def bid(self) -> Decimal | None:
        q = self._state.quote
        return q.bid if q else None

    @property
    def ask(self) -> Decimal | None:
        q = self._state.quote
        return q.ask if q else None

    @property
    def volume(self) -> int:
        q = self._state.quote
        return q.volume if q else 0

    @property
    def market_depth(self) -> MarketDepth | None:
        return self._state.depth

    @property
    def order_book(self) -> MarketDepth | None:
        return self._state.depth

    @property
    def is_live(self) -> bool:
        return self._state.is_subscribed

    @property
    def last_tick(self) -> QuoteSnapshot | None:
        # ponytail: last_tick aliases quote; VO tracks last_update instead
        return self._state.quote

    # ── Data Actions ──────────────────────────────────────────────────

    def refresh(self) -> QuoteSnapshot | None:
        """Pull latest quote into state."""
        provider = self._resolve_provider()
        quote = provider.get_quote(self._id)
        if quote is not None:
            with self._lock:
                self._state = self._state.with_quote(quote)
        return quote

    def depth(self) -> MarketDepth | None:
        """Fetch market depth into owned state and return it."""
        provider = self._resolve_provider()
        d = provider.get_depth(self._id)
        if d is not None:
            with self._lock:
                self._state = self._state.with_depth(d)
        return d

    def spread(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    def mid_price(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def statistics(self) -> dict:
        """Return current statistics snapshot."""
        q = self._state.quote
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "ltp": q.ltp if q else None,
            "bid": q.bid if q else None,
            "ask": q.ask if q else None,
            "volume": q.volume if q else 0,
            "high": q.high if q else None,
            "low": q.low if q else None,
            "open": q.open_ if q else None,
            "close": q.close if q else None,
            "spread": self.spread(),
            "mid_price": self.mid_price(),
        }

    def snapshot(self) -> dict:
        """Return full state snapshot."""
        return {
            "id": str(self._id),
            "state": {
                "quote": self._state.quote.__dict__ if self._state.quote else None,
                "depth": self._state.depth.__dict__ if self._state.depth else None,
                "is_subscribed": self._state.is_subscribed,
                "error": self._state.error,
            },
        }

    def serialize(self) -> dict:
        """JSON-serializable representation."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "lot_size": self.lot_size,
            "tick_size": str(self.tick_size),
        }
