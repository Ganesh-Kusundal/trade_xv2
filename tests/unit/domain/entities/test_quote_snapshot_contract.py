"""Quote (wire) ↔ QuoteSnapshot (product) conversion contract."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.candles.historical import InstrumentRef
from domain.entities.market import Quote, QuoteSnapshot
from domain.provenance import DataProvenance


@pytest.mark.unit
def test_quote_to_snapshot_derives_change_pct() -> None:
    ts = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    wire = Quote(
        symbol="RELIANCE",
        ltp=Decimal("1300"),
        open=Decimal("1280"),
        high=Decimal("1310"),
        low=Decimal("1275"),
        close=Decimal("1250"),
        volume=1_000_000,
        change=Decimal("50"),  # absolute
        timestamp=ts,
    )
    snap = wire.to_snapshot(exchange="NSE")
    assert isinstance(snap, QuoteSnapshot)
    assert snap.event_time == ts
    assert snap.instrument.symbol == "RELIANCE"
    assert snap.instrument.exchange == "NSE"
    assert snap.change_pct == Decimal("4")  # 50/1250*100
    assert snap.ltp == Decimal("1300")


@pytest.mark.unit
def test_snapshot_to_quote_restores_absolute_change() -> None:
    ts = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    snap = QuoteSnapshot(
        instrument=InstrumentRef(symbol="TCS", exchange="NSE"),
        ltp=Decimal("4000"),
        event_time=ts,
        provenance=DataProvenance.now("test", "unit"),
        close=Decimal("3900"),
        change_pct=Decimal("10"),
    )
    wire = snap.to_quote()
    assert wire.timestamp == ts
    assert wire.change == Decimal("390")  # 10% of 3900
