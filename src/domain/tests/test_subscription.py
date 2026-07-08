"""Unit tests for the Subscription tracked object lifecycle."""

from __future__ import annotations

from decimal import Decimal

from domain.instruments.instrument_id import InstrumentId
from domain.instruments.subscription import Subscription
from domain.tests._fakes import FakeEventBus


class _StubProviderSub:
    def __init__(self) -> None:
        self.is_active = True

    def unsubscribe(self) -> None:
        self.is_active = False


def _attach(sub: Subscription) -> _StubProviderSub:
    ps = _StubProviderSub()
    sub._attach(ps, teardown=lambda: None)
    return ps


def test_subscription_starts_inactive_until_attached():
    bus = FakeEventBus()
    iid = InstrumentId.equity("NSE", "RELIANCE")
    sub = Subscription(iid, event_bus=bus)
    assert sub.is_active is False
    assert sub.tick_count == 0


def test_subscription_counts_ticks_and_publishes():
    bus = FakeEventBus()
    iid = InstrumentId.equity("NSE", "RELIANCE")
    sub = Subscription(iid, event_bus=bus)
    _attach(sub)
    from domain.entities.market import QuoteSnapshot, MarketDepth
    from domain.candles.historical import InstrumentRef
    from domain.provenance import DataProvenance
    from datetime import datetime, timezone

    q = QuoteSnapshot(instrument=InstrumentRef("RELIANCE", "NSE"), ltp=Decimal("10"),
                      event_time=datetime.now(timezone.utc),
                      provenance=DataProvenance.now("fake", "r"))
    sub._on_tick(iid, q)
    sub._on_tick(iid, q)
    assert sub.tick_count == 2
    assert bus.count("TICK") == 2


def test_subscription_publishes_depth_updated():
    bus = FakeEventBus()
    iid = InstrumentId.equity("NSE", "RELIANCE")
    sub = Subscription(iid, event_bus=bus, depth=True)
    _attach(sub)
    from domain.entities.market import MarketDepth

    sub._on_tick(iid, MarketDepth(symbol="RELIANCE"))
    assert sub.depth_count == 1
    assert bus.count("DEPTH_UPDATED") == 1


def test_unsubscribe_tears_down_and_publishes_ended():
    bus = FakeEventBus()
    iid = InstrumentId.equity("NSE", "RELIANCE")
    sub = Subscription(iid, event_bus=bus)
    ps = _attach(sub)
    sub.unsubscribe()
    assert ps.is_active is False
    assert sub.is_active is False
    assert bus.count("SUBSCRIPTION_ENDED") == 1
