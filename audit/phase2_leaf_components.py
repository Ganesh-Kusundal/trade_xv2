"""
PHASE 2 — LEAF COMPONENT VALIDATION (v2 — using real signatures from runtime probing)
Tests real implementations with deterministic inputs.
No mocks except network boundary.
"""
import sys
import traceback
import pandas as pd
import numpy as np
from decimal import Decimal

RESULTS = []

def ok(name):
    RESULTS.append(("PASS", name))
    print(f"  [PASS] {name}")

def fail(name, reason):
    RESULTS.append(("FAIL", name, reason))
    print(f"  [FAIL] {name}: {reason}")


def _make_ohlcv(n=60, seed=42, symbol="MCX:CRUDEOIL26JULFUT"):
    """Build OHLCV DataFrame with the EXACT columns normalize_ohlcv requires."""
    np.random.seed(seed)
    close = 500 + np.cumsum(np.random.randn(n) * 2)
    dates = pd.date_range("2026-07-17 09:15", periods=n, freq="1min")
    return pd.DataFrame({
        "timestamp": dates,        # REQUIRED (discovered from runtime)
        "datetime":  dates,
        "open":  close - 0.5,
        "high":  close + 1.5,
        "low":   close - 1.5,
        "close": close,
        "volume": np.random.randint(200, 5000, n).astype(float),
        "symbol": symbol,
        "exchange": "MCX",
        "timeframe": "1m",
    })


# ── FeatureBuilder ──────────────────────────────────────────────────────────
def test_feature_builder():
    from analytics.core.feature_builder import FeatureBuilder

    df = _make_ohlcv(n=60)
    fb = FeatureBuilder()
    fs = fb.build(df, symbol="MCX:CRUDEOIL26JULFUT", exchange="MCX", timeframe="1m")

    assert not fs.data.empty, "FeatureSet.data is empty"
    assert "rsi"          in fs.data.columns, "rsi missing"
    assert "atr"          in fs.data.columns, "atr missing"
    assert "roc"          in fs.data.columns, "roc missing"
    assert "volume_spike" in fs.data.columns, "volume_spike missing"
    assert "returns"      in fs.data.columns, "returns missing"
    assert fs.summary["bar_count"] == 60
    assert 0 <= fs.summary["trend_score"] <= 100
    assert fs.summary["last_close"] > 0
    ok("FeatureBuilder.build() — rsi/atr/roc/volume_spike/returns, bar_count=60, trend_score in [0,100]")

    # Empty input → empty FeatureSet (not an exception)
    empty_fs = fb.build(pd.DataFrame(), symbol="TEST")
    assert empty_fs.data.empty
    ok("FeatureBuilder.build() — empty input returns empty FeatureSet")

    # volume_bars < 2 raises ValueError
    try:
        FeatureBuilder(volume_bars=1)
        fail("FeatureBuilder — volume_bars<2 should raise ValueError", "no exception raised")
    except ValueError:
        ok("FeatureBuilder.__init__() — volume_bars<2 raises ValueError")


# ── RiskManager ─────────────────────────────────────────────────────────────
def test_risk_manager():
    from application.oms._internal.risk_manager import RiskManager
    from application.oms._internal.risk_types import RiskConfig
    from application.oms._internal.margin_checker import MarginChecker

    class FakeCapital:
        def get_available_balance(self): return Decimal("100000")

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("80"),
        kill_switch=False,
    )
    # RiskManager requires position_manager (discovered at runtime)
    from application.oms.position_manager import PositionManager
    from infrastructure.event_bus.event_bus import EventBus
    pm = PositionManager(EventBus())
    rm = RiskManager(position_manager=pm, config=config, capital_provider=FakeCapital())

    snap = rm.snapshot()
    for key in ["kill_switch", "daily_pnl", "max_daily_loss_pct", "trading_state", "loss_circuit_breaker"]:
        assert key in snap, f"snapshot missing key: {key}"
    ok("RiskManager.snapshot() — all required keys present")

    assert rm.is_kill_switch_active() is False
    ok("RiskManager — kill_switch initially False")

    rm.set_kill_switch(True)
    assert rm.is_kill_switch_active() is True
    ok("RiskManager.set_kill_switch(True)")

    rm.set_kill_switch(False)
    assert rm.is_kill_switch_active() is False
    ok("RiskManager.set_kill_switch(False)")

    assert rm.daily_pnl == Decimal("0")
    ok("RiskManager.daily_pnl — starts at 0")

    rm.update_daily_pnl(Decimal("500"))
    assert rm.daily_pnl == Decimal("500")
    ok("RiskManager.update_daily_pnl(500)")

    rm.reset_daily_pnl()
    assert rm.daily_pnl == Decimal("0")
    ok("RiskManager.reset_daily_pnl() → 0")


# ── StrategyPipeline ─────────────────────────────────────────────────────────
def test_strategy_pipeline():
    from analytics.strategy.pipeline import StrategyPipeline, MomentumStrategy, BreakoutStrategy
    from analytics.strategy.models import SignalType, StrategyResult
    from analytics.strategy.evaluator_bridge import Candidate  # real location

    df = _make_ohlcv(n=50)
    # Add columns strategies probe
    df["rsi"] = np.linspace(40, 75, len(df))
    df["atr"] = 3.0
    df["roc"] = 0.5
    df["momentum"] = 0.3
    df["trend"] = "Uptrend"
    df["market_structure"] = "Breakout"

    candidate = Candidate(symbol="MCX:CRUDEOIL26JULFUT", exchange="MCX", score=100.0)
    pipeline = StrategyPipeline(strategies=[MomentumStrategy(), BreakoutStrategy()])
    results = pipeline.evaluate([candidate], {"MCX:CRUDEOIL26JULFUT": df})

    assert len(results) == 2, f"Expected 2 StrategyResult, got {len(results)}"
    for r in results:
        assert isinstance(r, StrategyResult)
        assert len(r.signals) == 1
        s = r.signals[0]
        assert s.symbol == "MCX:CRUDEOIL26JULFUT"
        assert s.signal_type in list(SignalType)
        assert 0.0 <= s.confidence <= 1.0
    ok("StrategyPipeline.evaluate() — 2 strategies × 1 candidate → valid signals")

    # evaluate_single
    sigs = pipeline.evaluate_single(candidate, df)
    assert len(sigs) == 2
    ok("StrategyPipeline.evaluate_single() — 2 signals returned")

    # Empty features → HOLD
    empty_sigs = pipeline.evaluate_single(candidate, pd.DataFrame())
    for s in empty_sigs:
        assert s.signal_type == SignalType.HOLD
    ok("StrategyPipeline — empty features → HOLD signals")


# ── EventBus ────────────────────────────────────────────────────────────────
def test_event_bus():
    from infrastructure.event_bus.event_bus import EventBus
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from domain.events.types import DomainEvent

    dlq = DeadLetterQueue()
    bus = EventBus(dead_letter_queue=dlq)

    received = []
    bus.subscribe("TEST_EVENT", lambda e: received.append(e))

    evt = DomainEvent.now("TEST_EVENT", {"value": 42}, symbol="MCX:CRUDE")
    bus.publish(evt)
    assert len(received) == 1
    assert received[0].payload["value"] == 42
    ok("EventBus.publish() — subscriber receives event with correct payload")

    # Duplicate suppression (same event_id)
    bus.publish(evt)
    assert len(received) == 1, f"Duplicate not suppressed: received={len(received)}"
    ok("EventBus — duplicate event_id suppressed")

    # Handler failure → DLQ
    def bad_handler(e): raise RuntimeError("handler failure")
    bus.subscribe("FAIL_EVENT", bad_handler)
    fail_evt = DomainEvent.now("FAIL_EVENT", {}, symbol="SYM")
    bus.publish(fail_evt)  # MUST NOT raise

    # DeadLetterQueue uses .stats() not .size() — discovered at runtime
    stats = dlq.stats()
    assert stats.get("pushed", 0) >= 1 or stats.get("size", 0) >= 1 or len(dlq.peek()) >= 1, \
        f"DLQ empty after handler failure: {stats}"
    ok("EventBus — handler exception → DLQ, not propagated")

    # Unsubscribe
    sub_id = bus.subscribe("UNSUB_TEST", lambda e: received.append(e))
    before = len(received)
    bus.unsubscribe(sub_id)
    bus.publish(DomainEvent.now("UNSUB_TEST", {}))
    assert len(received) == before
    ok("EventBus.unsubscribe() — handler not called after unsubscribe")


# ── PositionManager ─────────────────────────────────────────────────────────
def test_position_manager():
    from application.oms.position_manager import PositionManager
    from infrastructure.event_bus.event_bus import EventBus

    bus = EventBus()
    pm = PositionManager(event_bus=bus)

    # Real method is get_positions() not get_all_positions (discovered at runtime)
    positions = pm.get_positions()
    assert isinstance(positions, list)
    ok("PositionManager.get_positions() — returns list")

    net = pm.get_net_pnl()
    assert isinstance(net, Decimal)
    ok("PositionManager.get_net_pnl() — returns Decimal")


# ── TradingContext (minimal, no processed_trade_repository) ─────────────────
def test_trading_context():
    from application.oms.factory import create_trading_context
    from infrastructure.event_bus.event_bus import EventBus
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from infrastructure.event_bus.processed_trade_repository import ProcessedTradeRepository

    bus = EventBus()
    dlq = DeadLetterQueue()
    ptr = ProcessedTradeRepository()  # required for auto_cleanup

    ctx = create_trading_context(
        event_bus=bus,
        dead_letter_queue=dlq,
        processed_trade_repository=ptr,
        replay_events=False,
    )
    assert ctx is not None
    assert ctx.order_manager is not None
    assert ctx.position_manager is not None
    ok("TradingContext — instantiated via create_trading_context()")

    orders = ctx.order_manager.get_all_orders()
    assert isinstance(orders, list)
    ok("TradingContext.order_manager.get_all_orders() — returns list")


# ── RUN ─────────────────────────────────────────────────────────────────────
def run():
    print("=" * 70)
    print("PHASE 2 — LEAF COMPONENT VALIDATION (real signatures)")
    print("=" * 70)

    tests = [
        ("FeatureBuilder",    test_feature_builder),
        ("RiskManager",       test_risk_manager),
        ("StrategyPipeline",  test_strategy_pipeline),
        ("EventBus",          test_event_bus),
        ("PositionManager",   test_position_manager),
        ("TradingContext",    test_trading_context),
    ]

    for name, fn in tests:
        print(f"\n  -- {name} --")
        try:
            fn()
        except Exception as exc:
            fail(name, str(exc))
            traceback.print_exc()

    print()
    passes = [r for r in RESULTS if r[0] == "PASS"]
    fails  = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"PHASE 2 RESULT: {len(passes)} passed, {len(fails)} failed")
    if fails:
        for r in fails:
            print(f"  FAIL: {r[1]}: {r[2]}")
        sys.exit(1)

if __name__ == "__main__":
    run()
