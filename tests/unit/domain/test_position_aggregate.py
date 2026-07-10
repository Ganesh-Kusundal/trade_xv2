"""Tests for PositionAggregate (canonical: domain.aggregates)."""

from __future__ import annotations

from decimal import Decimal

from domain.aggregates import PositionAggregate
from domain.entities.position import Position


def test_position_aggregate_identity():
    pos = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500"))
    agg = PositionAggregate(position=pos, account_id="acc1")
    assert agg.account_id == "acc1"
    assert agg.instrument_id == "NSE:RELIANCE"
    assert agg.quantity == 10
