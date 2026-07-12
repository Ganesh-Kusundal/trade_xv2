"""HistoricalBar factories and replay/streaming compatibility."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain.candles.historical import HistoricalBar, InstrumentRef


def test_from_replay_symbol_timestamp_aliases() -> None:
    ts = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    bar = HistoricalBar.from_replay(
        symbol="TCS",
        timestamp=ts,
        open=100,
        high=105,
        low=98,
        close=103,
        volume=50_000,
        metadata={"regime": "trend"},
    )
    assert bar.symbol == "TCS"
    assert bar.timestamp == ts
    assert bar.close == Decimal("103")
    assert bar.to_dict()["close"] == 103.0
    assert bar.to_dict()["regime"] == "trend"


def test_from_live_bucket_carries_close_time_and_tick_count() -> None:
    open_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    close_time = datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc)
    bar = HistoricalBar.from_live_bucket(
        symbol="REL",
        exchange="NSE",
        timeframe="1m",
        open_time=open_time,
        close_time=close_time,
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=40.0,
        tick_count=4,
    )
    assert bar.open_time == open_time
    assert bar.close_time == close_time
    assert bar.tick_count == 4
    assert bar.instrument == InstrumentRef("REL", "NSE")
