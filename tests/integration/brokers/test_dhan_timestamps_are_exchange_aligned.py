"""Regression tests for the Dhan timestamp / sequence / dedup remediation.

Review finding: "Dhan quotes carry NO exchange timestamp, so downstream
dedup/ordering and the live candle aggregator have no reliable time for Dhan ticks."

These tests pin:
  R1  The Dhan feed stamps every tick with an arrival ``timestamp`` (timezone
      aware) and a synthesized per-instrument monotonic ``sequence``.
  R2  TickRouter normalizes a Dhan-style frame's arrival time into
      ``MarketTick.event_time`` (``_parse_exchange_time`` prefers a non-null
      ``timestamp``).
  R3  Within the dedup window, an identical re-delivered Dhan tick (same ltp)
      is dropped by ``dedup_drop``; a tick with a different ltp is not.

Run:
  cd /Users/apple/Downloads/Trade_XV2 && \
    ./venv/bin/python -m pytest tests/integration/brokers/test_dhan_timestamps_are_exchange_aligned.py -q
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest


def _make_router():
    from application.streaming.tick_router import TickRouter

    router = object.__new__(TickRouter)
    router._dedup_seen = {}
    return router


class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


# =============================================================================
# R1 — Dhan feed stamps an arrival timestamp + synthesized sequence
# =============================================================================


def test_dhan_feed_stamps_timestamp_and_sequence():
    """_transform_quote stamps arrival time; publisher assigns sequence on publish."""
    from brokers.providers.dhan.websocket._helpers import _to_decimal
    from brokers.providers.dhan.websocket.market_feed import DhanMarketFeed
    from brokers.providers.dhan.websocket.publish import MarketFeedPublisher

    feed = DhanMarketFeed(client_id="CID", access_token="TOK", instruments=None)

    q = feed._transform_quote(
        {"security_id": "123", "last_price": 100.5, "symbol": "RELIANCE", "ltp": 100.5}
    )
    assert isinstance(q.get("timestamp"), datetime)
    assert q["timestamp"].tzinfo is not None

    bus = _FakeBus()
    feed._event_bus = bus
    feed._publisher = MarketFeedPublisher(
        bus,
        feed._next_sequence,
        to_decimal=_to_decimal,
    )
    feed._publish_tick(q)

    assert isinstance(q.get("sequence"), int) and q["sequence"] >= 1

    ticks = [e for e in bus.events if e.event_type == "TICK"]
    assert len(ticks) == 1
    assert ticks[0].payload["quote"].timestamp is not None


# =============================================================================
# R2 — TickRouter preserves a Dhan-style arrival timestamp into event_time
# =============================================================================


def test_dhan_orchestrator_prefers_arrival_timestamp():
    """_normalize_tick uses a Dhan frame's arrival ``timestamp`` for event_time
    (not the local ``now`` fallback)."""
    from application.streaming.tick_router import TickRouter
    from domain.entities.market import MarketTick

    ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    frame = {"symbol": "RELIANCE", "exchange": "NSE", "ltp": 100.0, "timestamp": ts}
    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

    tick = TickRouter._normalize_tick(frame, "s1", "dhan", now)
    assert isinstance(tick, MarketTick)
    assert tick.event_time == ts
    assert tick.broker_id == "dhan"
    assert tick.sequence is None  # no source sequence on the frame here


# =============================================================================
# R3 — Dhan dedup: identical re-delivery dropped, different ltp not dropped
# =============================================================================


def test_dhan_dedup_identical_dropped_different_ltp_kept():
    """Within the window, a re-delivered Dhan tick at the same ltp is dropped;
    a tick with a different ltp is not."""
    router = _make_router()

    ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    # First tick is recorded (not dropped).
    assert router.dedup_drop("RELIANCE:NSE", ts, 1, ltp=100.0, trusted_time=False) is False
    # Re-delivery at the same ltp within the coarse bucket is dropped.
    assert router.dedup_drop("RELIANCE:NSE", ts, 2, ltp=100.0, trusted_time=False) is True
    # Different ltp is a distinct tick and is kept.
    assert router.dedup_drop("RELIANCE:NSE", ts, 3, ltp=101.0, trusted_time=False) is False


def test_dhan_dedup_no_false_drop_for_trusted_time():
    """Upstox frames (trusted exchange time) rely only on the primary key and
    are not subject to the coarse ltp-bucket fallback."""
    router = _make_router()

    ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    # trusted_time=True (exchange_timestamp present) → fallback not applied.
    assert router.dedup_drop("X:NSE", ts, 1, ltp=100.0, trusted_time=True) is False
    assert router.dedup_drop("X:NSE", ts, 2, ltp=100.0, trusted_time=True) is False
