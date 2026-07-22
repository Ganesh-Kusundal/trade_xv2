"""GapDetector must not flag pure weekend/holiday spans as data gaps.

Regression guard: a lookback window ending "today" almost always starts on
some earlier weekend day. Treating that as a Gap made scripts/sync_datalake.py's
_require_complete_federated_fetch reject the majority of real syncs even
though the fetch itself was complete (degraded=False) — there was never a
bar to fetch on a non-trading day.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from application.data.gap_detector import GapDetector
from application.data.historical_coordinator import HistoricalQuery
from domain.candles.historical import InstrumentRef
from domain.provenance import DataProvenance
from domain.candles.historical import HistoricalBar

INSTRUMENT = InstrumentRef(symbol="RELIANCE", exchange="NSE")


def _bar(d: date) -> HistoricalBar:
    return HistoricalBar(
        instrument=INSTRUMENT,
        timeframe="1m",
        event_time=datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=100,
        provenance=DataProvenance.now(broker_id="dhan", request_id="r1"),
    )


def _query(from_date: date, to_date: date) -> HistoricalQuery:
    return HistoricalQuery(instrument=INSTRUMENT, timeframe="1m", from_date=from_date, to_date=to_date)


def test_weekend_only_start_gap_is_not_reported():
    # 2026-07-19 is a Sunday; first real trading day is Monday 2026-07-20.
    bars = [_bar(date(2026, 7, 20)), _bar(date(2026, 7, 21))]
    gaps = GapDetector().detect(bars, _query(date(2026, 7, 19), date(2026, 7, 21)))
    assert gaps == []


def test_real_missing_trading_day_is_still_reported():
    # Data stops Friday 2026-07-17; Mon 2026-07-20 and Tue 2026-07-21 are
    # real trading days with no bars — a genuine end-of-range gap.
    bars = [_bar(date(2026, 7, 17))]
    gaps = GapDetector().detect(bars, _query(date(2026, 7, 17), date(2026, 7, 21)))
    assert len(gaps) == 1
    assert gaps[0].reason == "missing_from_end"
    assert gaps[0].start == date(2026, 7, 18)


def test_empty_bars_over_weekend_only_range_is_not_reported():
    gaps = GapDetector().detect([], _query(date(2026, 7, 18), date(2026, 7, 19)))
    assert gaps == []


def test_empty_bars_over_trading_range_is_reported():
    gaps = GapDetector().detect([], _query(date(2026, 7, 20), date(2026, 7, 21)))
    assert len(gaps) == 1
    assert gaps[0].reason == "all_failed"
