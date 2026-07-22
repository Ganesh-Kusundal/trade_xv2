"""market_tick_from_event propagates sequence/session_id from TICK payload."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from application.streaming.live_tick_pipeline import market_tick_from_event
from domain import Quote
from domain.events.types import DomainEvent


@pytest.mark.unit
def test_market_tick_from_event_propagates_sequence_and_session() -> None:
    ts = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    quote = Quote(symbol="RELIANCE", ltp=Decimal("2500"), volume=100, timestamp=ts)
    event = DomainEvent(
        event_type="TICK",
        timestamp=ts,
        payload={
            "quote": quote,
            "exchange": "NSE",
            "sequence": 42,
            "session_id": "sess-abc",
        },
        symbol="RELIANCE",
        source="DhanMarketFeed",
    )
    tick = market_tick_from_event(event)
    assert tick is not None
    assert tick.sequence == 42
    assert tick.session_id == "sess-abc"
    assert tick.broker_id == "DhanMarketFeed"


@pytest.mark.unit
def test_market_tick_from_event_flat_payload_sequence() -> None:
    ts = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    event = DomainEvent(
        event_type="TICK",
        timestamp=ts,
        payload={"ltp": "100", "volume": 1, "exchange": "NSE", "sequence": 7},
        symbol="INFY",
        source="synthetic",
    )
    tick = market_tick_from_event(event)
    assert tick is not None
    assert tick.sequence == 7
    assert tick.session_id == ""
