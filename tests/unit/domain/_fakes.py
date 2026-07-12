"""Shared fakes for domain unit/contract tests.

These implement the real provider/bus *ports* with in-memory data, so domain
logic is tested against real collaborators (no mocks of domain behavior).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from domain.candles.historical import InstrumentRef
from domain.entities.market import DepthLevel, MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain as OptionChainVO
from domain.provenance import DataProvenance


def make_quote(symbol: str, exchange: str, ltp: Decimal = Decimal("100.5")) -> QuoteSnapshot:
    return QuoteSnapshot(
        instrument=InstrumentRef(symbol, exchange),
        ltp=ltp,
        event_time=datetime.now(timezone.utc),
        provenance=DataProvenance.now("fake", "req-1"),
        volume=1234,
        bid=ltp - Decimal("0.5"),
        ask=ltp + Decimal("0.5"),
    )


def make_depth(symbol: str) -> MarketDepth:
    return MarketDepth(
        symbol=symbol,
        bids=[DepthLevel(Decimal("100"), 10, 2), DepthLevel(Decimal("99.9"), 5, 1)],
        asks=[DepthLevel(Decimal("100.5"), 8, 1), DepthLevel(Decimal("100.6"), 4, 1)],
    )


class FakeEventBus:
    """In-memory DomainEventBus that records every published event."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self._handlers: dict[str, list[Callable]] = {}

    def publish(self, event) -> None:
        self.events.append((event.event_type, dict(event.payload)))

    def subscribe(self, event_type: str, handler: Callable) -> str:
        self._handlers.setdefault(event_type, []).append(handler)
        return f"{event_type}-{len(self._handlers[event_type])}"

    def unsubscribe(self, token: str) -> bool:
        return True

    def types(self) -> list[str]:
        return [e[0] for e in self.events]

    def count(self, event_type: str) -> int:
        return sum(1 for t, _ in self.events if t == event_type)


class _ProviderSubscription:
    def __init__(self) -> None:
        self.is_active = True

    def unsubscribe(self) -> None:
        self.is_active = False


class FakeProvider:
    """In-memory DataProvider for tests and notebooks."""

    def __init__(self) -> None:
        self.name = "fake"
        self._quotes: dict[tuple[str, str], QuoteSnapshot] = {}
        self._depths: dict[tuple[str, str], MarketDepth] = {}
        self._chains: dict[tuple[str, str], OptionChainVO] = {}
        self._callbacks: dict[tuple[str, str], Callable] = {}

    # ── seeding helpers ─────────────────────────────────────────────

    def seed_quote(self, symbol: str, exchange: str, ltp: Decimal = Decimal("100.5")) -> None:
        self._quotes[(symbol, exchange)] = make_quote(symbol, exchange, ltp)

    def seed_depth(self, symbol: str, exchange: str) -> None:
        self._depths[(symbol, exchange)] = make_depth(symbol)

    def seed_chain(self, underlying: str, exchange: str, vo: OptionChainVO) -> None:
        self._chains[(underlying, exchange)] = vo

    # ── DataProvider protocol ──────────────────────────────────────

    def get_quote(self, instrument_id):
        return self._quotes.get((instrument_id.underlying, instrument_id.exchange))

    def get_history(self, instrument_id, *, timeframe="1D", lookback_days=120,
                    from_date=None, to_date=None):
        # Prefer domain bars (list); export to DataFrame only at boundary.
        return self.get_history_series(
            instrument_id,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        ).bars

    def get_history_series(
        self,
        instrument_id,
        *,
        timeframe="1D",
        lookback_days=120,
        from_date=None,
        to_date=None,
    ):
        from domain.candles.historical import HistoricalBar, HistoricalSeries
        from domain.provenance import DataProvenance

        ref = InstrumentRef(
            symbol=instrument_id.underlying, exchange=instrument_id.exchange
        )
        now = datetime.now(timezone.utc)
        bars = [
            HistoricalBar(
                instrument=ref,
                timeframe=timeframe,
                event_time=now,
                open=Decimal("1"),
                high=Decimal("2"),
                low=Decimal("1"),
                close=Decimal("1.5"),
                volume=10,
                provenance=DataProvenance.now("fake", "hist-1"),
            ),
            HistoricalBar(
                instrument=ref,
                timeframe=timeframe,
                event_time=now,
                open=Decimal("1.5"),
                high=Decimal("2"),
                low=Decimal("1"),
                close=Decimal("2"),
                volume=20,
                provenance=DataProvenance.now("fake", "hist-2"),
            ),
        ]
        return HistoricalSeries(
            bars=bars,
            coverage=None,
            instrument=ref,
            timeframe=timeframe,
        )

    def get_depth(self, instrument_id):
        return self._depths.get((instrument_id.underlying, instrument_id.exchange))

    def get_option_chain(self, underlying, *, expiry=None):
        key = (underlying.underlying, underlying.exchange)
        return self._chains.get(key, OptionChainVO(underlying=underlying.underlying,
                                                     exchange=underlying.exchange, expiry=expiry or ""))

    def get_future_chain(self, underlying):
        return FutureChain(underlying=underlying.underlying, exchange=underlying.exchange)

    def subscribe(self, instrument_id, callback: Callable, *, depth: bool = False):
        self._callbacks[(instrument_id.underlying, instrument_id.exchange)] = callback
        return _ProviderSubscription()

    def unsubscribe(self, subscription) -> None:
        subscription.unsubscribe()

    def history_batch(self, instrument_ids, *, timeframe="1D", lookback_days=120):
        return pd.DataFrame()

    def list_instruments(self, exchange=None):
        return []

    def get_quotes_batch(self, instrument_ids):
        return [self.get_quote(iid) for iid in instrument_ids]

    # ── test helper ─────────────────────────────────────────────────

    def fire_tick(self, symbol: str, exchange: str, payload) -> None:
        cb = self._callbacks.get((symbol, exchange))
        if cb is not None:
            from domain.instruments.instrument_id import InstrumentId
            cb(InstrumentId.equity(exchange, symbol), payload)
