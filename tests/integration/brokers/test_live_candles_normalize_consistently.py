"""Regression tests for the live tick→candle (OHLCV) aggregator.

Review finding: "OHLC/candle generation effectively ABSENT for live data —
candles are REST-only; live ticks never aggregate into candles."

These tests pin the new :class:`CandleAggregator` behaviour and its wiring into
the :class:`StreamOrchestrator` fan-out path. The runtime package is
gitignored, so we lazy-import it inside each test and ``pytest.skip`` cleanly if
it cannot be imported in the current environment.

Run:
  cd /Users/apple/Downloads/Trade_XV2 && \
    ./venv/bin/python -m pytest tests/integration/brokers/test_live_candles_normalize_consistently.py -q
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _import_runtime():
    """Lazy-import the (gitignored) runtime package; skip if unimportable."""
    try:
        from application.streaming.candle_aggregator import (
            CandleAggregator,
            parse_timeframe,
        )
        from application.streaming.orchestrator import (
            MarketTick,
            StreamOrchestrator,
        )
        from domain.candles.historical import HistoricalBar, InstrumentRef
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"runtime module not importable: {exc}")
    return (
        CandleAggregator,
        HistoricalBar,
        parse_timeframe,
        MarketTick,
        StreamOrchestrator,
        InstrumentRef,
    )


def _tick(symbol, ltp, volume, ts, exchange="NSE"):
    from decimal import Decimal

    from domain.entities.market import MarketTick
    from domain.provenance import DataProvenance

    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )
    return MarketTick(
        instrument=InstrumentRef(symbol=symbol, exchange=exchange),
        ltp=Decimal(str(ltp)),
        event_time=ts,
        provenance=DataProvenance.now("test", "stream"),
        volume=int(volume),
        bid=None,
        ask=None,
        broker_id="test",
        session_id="s1",
        sequence=None,
    )


# =============================================================================
# 1. Basic 1m OHLCV aggregation with correct boundary emission
# =============================================================================


def test_1m_candle_ohlcv_and_boundary():
    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )

    emitted = []
    agg = CandleAggregator(on_candle=emitted.append, timeframes=("1m",))

    # Bucket 1: 10:00:00–10:00:59 UTC. Prices 100,102,99,101 (vol 10 each).
    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    agg.update(_tick("REL", 100, 10, base))
    agg.update(_tick("REL", 102, 10, base.replace(second=15)))
    agg.update(_tick("REL", 99, 10, base.replace(second=30)))
    agg.update(_tick("REL", 101, 10, base.replace(second=45)))

    # Cross into next 1m bucket (10:01:00) → bucket 1 is emitted.
    agg.update(_tick("REL", 103, 10, base.replace(minute=1, second=0)))

    assert len(emitted) == 1
    c = emitted[0]
    assert (c.symbol, c.exchange, c.timeframe) == ("REL", "NSE", "1m")
    assert c.open == 100.0
    assert c.high == 102.0
    assert c.low == 99.0
    assert c.close == 101.0
    assert c.volume == 40.0
    assert c.tick_count == 4
    assert c.open_time.timestamp() == base.timestamp()
    assert c.close_time.timestamp() == base.replace(minute=1, second=0).timestamp()


# =============================================================================
# 2. Multi-timeframe buckets coexist per (symbol, timeframe)
# =============================================================================


def test_multi_timeframe_per_symbol():
    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )

    emitted = []
    agg = CandleAggregator(on_candle=emitted.append, timeframes=("1m", "5m"))

    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    # Two 1m buckets worth of ticks; only 1m boundary is crossed once.
    # 10:00 tick (50) opens the 10:00 1m + 5m buckets.
    agg.update(_tick("AAA", 50, 1, base))
    # 10:01 tick (60): closes the 10:00 1m bucket (only the 50 tick), opens the
    # 10:01 1m bucket. Still inside the 10:00–10:04 5m bucket → merged.
    agg.update(_tick("AAA", 60, 1, base.replace(minute=1)))

    candles_by_tf = {c.timeframe: c for c in emitted}
    assert set(candles_by_tf) == {"1m"}
    # The emitted 1m candle holds only the 10:00 tick (50); the 60 tick is the
    # OPEN of the next bucket.
    assert candles_by_tf["1m"].close == 50.0
    assert candles_by_tf["1m"].open_time.timestamp() == base.timestamp()

    # Now cross the 5m boundary (10:05:00) → both 1m and 5m open buckets emit.
    agg.update(_tick("AAA", 70, 1, base.replace(minute=5)))
    candles_by_tf = {c.timeframe: c for c in emitted}
    assert set(candles_by_tf) == {"1m", "5m"}
    # 5m candle spans 10:00/10:01/10:05 ticks: open 50, high 60, low 50, close 70.
    assert candles_by_tf["5m"].open == 50.0
    assert candles_by_tf["5m"].high == 60.0
    assert candles_by_tf["5m"].low == 50.0
    assert candles_by_tf["5m"].close == 60.0
    assert candles_by_tf["5m"].volume == 2.0
    assert candles_by_tf["5m"].tick_count == 2


# =============================================================================
# 3. Two symbols are bucketed independently
# =============================================================================


def test_independent_symbols():
    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )

    emitted = []
    agg = CandleAggregator(on_candle=emitted.append, timeframes=("1m",))

    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    agg.update(_tick("X", 10, 5, base))
    agg.update(_tick("Y", 20, 7, base))
    agg.update(_tick("X", 12, 5, base.replace(second=30)))
    # Cross boundary for both. X=11 opens X's 10:01 bucket; Y=21 opens Y's.
    agg.update(_tick("X", 11, 5, base.replace(minute=1)))
    agg.update(_tick("Y", 21, 7, base.replace(minute=1)))

    by_sym = {c.symbol: c for c in emitted}
    assert set(by_sym) == {"X", "Y"}
    # X 10:00 bucket saw ticks 10 and 12 → high 12, low 10, vol 10.
    assert by_sym["X"].high == 12.0 and by_sym["X"].low == 10.0
    assert by_sym["X"].volume == 10.0
    # Y 10:00 bucket saw only the 20 tick (the 21 is in the next bucket).
    assert by_sym["Y"].open == 20.0 and by_sym["Y"].high == 20.0
    assert by_sym["Y"].low == 20.0 and by_sym["Y"].close == 20.0
    assert by_sym["Y"].volume == 7.0


# =============================================================================
# 4. Late ticks for an already-closed window are discarded
# =============================================================================


def test_late_tick_discarded():
    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )

    emitted = []
    agg = CandleAggregator(on_candle=emitted.append, timeframes=("1m",))

    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    agg.update(_tick("L", 100, 1, base))
    agg.update(_tick("L", 110, 1, base.replace(minute=1)))  # closes 10:00 bucket, opens 10:01

    # Late tick referencing 10:00:30 (already closed) must be ignored by default.
    agg.update(_tick("L", 999, 50, base.replace(second=30)))
    agg.update(_tick("L", 120, 1, base.replace(minute=2)))

    assert len(emitted) == 2
    assert emitted[0].open == 100.0 and emitted[0].close == 100.0
    assert emitted[0].high == 100.0 and emitted[0].low == 100.0
    assert emitted[0].volume == 1.0
    assert emitted[1].open == 110.0 and emitted[1].close == 110.0


def test_late_tick_correction():
    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )

    emitted = []
    agg = CandleAggregator(on_candle=emitted.append, timeframes=("1m",))

    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    agg.update(_tick("L", 100, 1, base))
    agg.update(_tick("L", 110, 1, base.replace(minute=1)))
    before = len(emitted)
    agg.update(_tick("L", 105, 2, base.replace(second=30)), is_correction=True)
    assert len(emitted) == before + 1
    corrected = emitted[-1]
    assert corrected.close == 105.0
    assert corrected.volume == 2.0


# =============================================================================
# 5. Wiring: orchestrator feeds aggregator without breaking fan-out (off default)
# =============================================================================


def test_orchestrator_feeds_aggregator_when_attached():
    (
        CandleAggregator,
        HistoricalBar,
        parse_timeframe,
        MarketTick,
        StreamOrchestrator,
        InstrumentRef,
    ) = _import_runtime()

    emitted = []
    agg = CandleAggregator(on_candle=emitted.append, timeframes=("1m",))

    # Build an orchestrator with the aggregator attached via constructor.
    orch = StreamOrchestrator(registry=None, router=None, candle_aggregator=agg)

    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    tick = _tick("Z", 100, 1, base)
    # _deliver_tick is async but the aggregation path is synchronous inside it;
    # call it directly. No consumers are registered, so fan-out is a no-op.
    import asyncio

    asyncio.run(orch._tick_router.deliver_tick("s1", tick))

    # Aggregator received the tick (off-by-default behavior preserved: when no
    # aggregator is attached nothing happens).
    assert orch._candle_aggregator is agg
    assert agg.open_symbols() == {"Z:NSE"}

    # Detach via attach_candle_aggregator(None).
    orch.attach_candle_aggregator(None)
    assert orch._candle_aggregator is None


def test_parse_timeframe():
    CandleAggregator, HistoricalBar, parse_timeframe, MarketTick, _, InstrumentRef = (
        _import_runtime()
    )
    assert parse_timeframe("1m") == 60
    assert parse_timeframe("5m") == 300
    assert parse_timeframe("15m") == 900
    assert parse_timeframe("1h") == 3600
    assert parse_timeframe("30m") == 1800
    assert parse_timeframe("2h") == 7200
    assert parse_timeframe("1d") == 86400
    with pytest.raises(ValueError):
        parse_timeframe("bogus")
