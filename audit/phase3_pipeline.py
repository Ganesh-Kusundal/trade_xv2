"""
PHASE 3 — PIPELINE VALIDATION
Exercises the real end-to-end backend pipeline:
FeatureBuilder → StrategyPipeline → EventBus propagation
Asserts every stage executes, every event propagates, no silent failures.
"""
import sys
import traceback
import pandas as pd
import numpy as np
from decimal import Decimal
from typing import List

STAGE_LOG: List[str] = []
EVENTS_RECEIVED: List[object] = []

def run():
    print("=" * 70)
    print("PHASE 3 — PIPELINE VALIDATION")
    print("=" * 70)

    try:
        from analytics.core.feature_builder import FeatureBuilder
        from analytics.strategy.pipeline import StrategyPipeline, MomentumStrategy, BreakoutStrategy
        from analytics.strategy.models import Candidate, SignalType
        from infrastructure.event_bus.event_bus import EventBus
        from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
        from domain.events.types import DomainEvent
    except ImportError as exc:
        print(f"PHASE FAILED: PHASE 3 — PIPELINE VALIDATION")
        print(f"REASON: {exc}")
        sys.exit(1)

    dlq = DeadLetterQueue()
    bus = EventBus(dead_letter_queue=dlq)
    bus.subscribe("SIGNAL_GENERATED", lambda e: EVENTS_RECEIVED.append(e))
    bus.subscribe("PIPELINE_COMPLETE", lambda e: EVENTS_RECEIVED.append(e))

    # ── STAGE 1: Market Data (synthetic OHLCV) ────────────────────────────
    np.random.seed(99)
    n = 60
    close = 500 + np.cumsum(np.random.randn(n) * 1.5)
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-07-17 09:15", periods=n, freq="1min"),
        "open":  close - 0.5, "high": close + 1.5,
        "low":   close - 1.5, "close": close,
        "volume": np.random.randint(200, 5000, n),
        "symbol": "MCX:CRUDEOIL26JULFUT",
        "exchange": "MCX",
        "timeframe": "1m",
    })
    STAGE_LOG.append("STAGE_1:market_data_ingested")
    print(f"  [OK]  STAGE 1: Market data ingested ({n} bars)")

    # ── STAGE 2: FeatureBuilder ───────────────────────────────────────────
    fb = FeatureBuilder()
    fs = fb.build(df, symbol="MCX:CRUDEOIL26JULFUT", exchange="MCX", timeframe="1m")
    assert not fs.data.empty, "FAIL: FeatureSet empty after build"
    assert "rsi" in fs.data.columns
    assert "atr" in fs.data.columns
    STAGE_LOG.append("STAGE_2:features_built")
    print(f"  [OK]  STAGE 2: Features built — {list(fs.data.columns)}")

    # ── STAGE 3: StrategyPipeline ─────────────────────────────────────────
    pipeline = StrategyPipeline(strategies=[MomentumStrategy(), BreakoutStrategy()])
    candidate = Candidate(symbol="MCX:CRUDEOIL26JULFUT", exchange="MCX")
    results = pipeline.evaluate([candidate], {"MCX:CRUDEOIL26JULFUT": fs.data})
    assert len(results) == 2
    signals_generated = [s for r in results for s in r.signals]
    assert len(signals_generated) > 0
    STAGE_LOG.append("STAGE_3:strategies_evaluated")
    for r in results:
        for s in r.signals:
            print(f"  [OK]  STAGE 3: {r.strategy} → {s.signal_type.value} confidence={s.confidence}")

    # ── STAGE 4: Signal → EventBus publish ───────────────────────────────
    for sig in signals_generated:
        evt = DomainEvent.now(
            "SIGNAL_GENERATED",
            {
                "symbol":      sig.symbol,
                "signal_type": sig.signal_type.value,
                "confidence":  sig.confidence,
                "strategy":    sig.strategy,
            },
            symbol=sig.symbol,
        )
        bus.publish(evt)
    STAGE_LOG.append("STAGE_4:signals_published")

    completion_evt = DomainEvent.now("PIPELINE_COMPLETE", {"stage_log": STAGE_LOG})
    bus.publish(completion_evt)

    # ── ASSERT: no event loss ─────────────────────────────────────────────
    signal_events = [e for e in EVENTS_RECEIVED if e.event_type == "SIGNAL_GENERATED"]
    pipeline_events = [e for e in EVENTS_RECEIVED if e.event_type == "PIPELINE_COMPLETE"]

    assert len(signal_events) == len(signals_generated), (
        f"Event loss: published {len(signals_generated)} signals, "
        f"received {len(signal_events)}"
    )
    assert len(pipeline_events) == 1
    assert dlq.size() == 0, f"DLQ has entries — silent handler failures: {dlq.size()}"

    # ── ASSERT: stage ordering ────────────────────────────────────────────
    assert STAGE_LOG == [
        "STAGE_1:market_data_ingested",
        "STAGE_2:features_built",
        "STAGE_3:strategies_evaluated",
        "STAGE_4:signals_published",
    ], f"Stage ordering violated: {STAGE_LOG}"

    print(f"\n  [EVENTS_RECEIVED] {len(EVENTS_RECEIVED)} total")
    print(f"  [DLQ size]        {dlq.size()}")
    print(f"  [Stage log]       {STAGE_LOG}")
    print(f"\nPHASE 3 RESULT: PIPELINE VALIDATED — no event loss, no silent failures")

if __name__ == "__main__":
    run()
