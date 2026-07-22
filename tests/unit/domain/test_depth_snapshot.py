"""DepthSnapshot product contract — mirrors QuoteSnapshot boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.candles.historical import InstrumentRef
from domain.entities.market import DepthKind, DepthLevel, DepthSnapshot, MarketDepth
from domain.provenance import DataProvenance


@pytest.mark.unit
def test_market_depth_snapshot_returns_depth_snapshot() -> None:
    ts = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    depth = MarketDepth(
        symbol="RELIANCE",
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        bids=[DepthLevel(Decimal("100"), 10, 2)],
        asks=[DepthLevel(Decimal("100.5"), 8, 1)],
        depth_type=DepthKind.DEPTH_5,
        timestamp=ts,
    )
    snap = depth.snapshot(provenance=DataProvenance.now("test", "depth"))
    assert isinstance(snap, DepthSnapshot)
    assert snap.instrument.symbol == "RELIANCE"
    assert snap.depth_type == DepthKind.DEPTH_5
    assert snap.timestamp == ts
    assert snap.bids[0].price == Decimal("100")
    assert snap.asks[0].price == Decimal("100.5")
    assert snap.provenance is not None


@pytest.mark.unit
def test_depth_snapshot_dict_has_no_broker_tokens() -> None:
    depth = MarketDepth(symbol="INFY")
    snap = depth.snapshot(exchange="NSE")
    payload = snap.snapshot()
    assert "security_id" not in payload
    assert "instrument_token" not in payload
    assert payload["instrument"] == "INFY:NSE"
