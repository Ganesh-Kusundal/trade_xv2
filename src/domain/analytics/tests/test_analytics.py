"""Tests for AnalyticsAggregate."""

from __future__ import annotations

from decimal import Decimal

from domain.analytics import AnalyticsAggregate
from domain.analytics.analytics import AnalyticsSnapshot


def test_initial_snapshot():
    agg = AnalyticsAggregate(account_id="acc1")
    assert agg.snapshot.total_pnl == Decimal("0")
    assert agg.snapshot.trade_count == 0


def test_record_trade():
    agg = AnalyticsAggregate(account_id="acc1")
    agg.record_trade(Decimal("100"))
    agg.record_trade(Decimal("-30"))
    assert agg.snapshot.total_pnl == Decimal("70")
    assert agg.snapshot.realized_pnl == Decimal("70")
    assert agg.snapshot.trade_count == 2


def test_update_replaces_snapshot():
    agg = AnalyticsAggregate(account_id="acc1")
    snap = AnalyticsSnapshot(total_pnl=Decimal("500"), trade_count=10, win_rate=0.6)
    agg.update(snap)
    assert agg.snapshot.total_pnl == Decimal("500")
    assert agg.snapshot.win_rate == 0.6


def test_equality_by_account_id():
    a1 = AnalyticsAggregate(account_id="x")
    a2 = AnalyticsAggregate(account_id="x")
    a3 = AnalyticsAggregate(account_id="y")
    assert a1 == a2
    assert a1 != a3


def test_repr():
    agg = AnalyticsAggregate(account_id="acc1")
    assert "acc1" in repr(agg)
