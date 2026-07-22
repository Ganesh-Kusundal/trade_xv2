"""Timezone enforcement on market entities."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.candles.historical import InstrumentRef
from domain.entities.market import MarketDepth, MarketTick, Quote, QuoteSnapshot
from domain.provenance import DataProvenance


def test_market_tick_rejects_naive_event_time() -> None:
    with pytest.raises(ValueError, match="MarketTick.event_time"):
        MarketTick(
            instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
            ltp=Decimal("100"),
            event_time=datetime(2024, 1, 1),
            provenance=DataProvenance.now("dhan", "t"),
        )


def test_quote_snapshot_rejects_naive_event_time() -> None:
    with pytest.raises(ValueError, match="QuoteSnapshot.event_time"):
        QuoteSnapshot(
            instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
            ltp=Decimal("100"),
            event_time=datetime(2024, 1, 1),
            provenance=DataProvenance.now("dhan", "t"),
        )


def test_quote_allows_none_timestamp() -> None:
    q = Quote(symbol="RELIANCE", timestamp=None)
    assert q.timestamp is None


def test_quote_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="Quote.timestamp"):
        Quote(symbol="RELIANCE", timestamp=datetime(2024, 1, 1))


def test_market_depth_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="MarketDepth.timestamp"):
        MarketDepth(symbol="RELIANCE", timestamp=datetime(2024, 1, 1))
