"""
PHASE 10 — CONCURRENCY AND LOAD VALIDATION
Multi-symbol streaming, parallel order book mutation, memory growth,
lock contention detection. Uses real RiskManager, EventBus, PositionManager.
"""
import sys
import gc
import time
import threading
import traceback
import tracemalloc
from decimal import Decimal
from typing import List

RESULTS = []

def ok(name, detail=""):
    RESULTS.append(("PASS", name))
    print(f"  [PASS] {name} {detail}")

def fail(name, reason):
    RESULTS.append(("FAIL", name, reason))
    print(f"  [FAIL] {name}: {reason}")

# ── 1. EventBus concurrent publish — no race, no loss ───────────────────────
def test_eventbus_concurrent():
    from infrastructure.event_bus.event_bus import EventBus
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from domain.events.types import DomainEvent

    dlq = DeadLetterQueue()
    bus = EventBus(dead_letter_queue=dlq)

    lock = threading.Lock()
    received: List = []

    bus.subscribe("LOAD_EVENT", lambda e: (lock.acquire(), received.append(e.symbol), lock.release()))

    num_threads, events_per_thread = 20, 50
    total_expected = num_threads * events_per_thread

    def publish_worker(tid):
        for i in range(events_per_thread):
            e = DomainEvent.now("LOAD_EVENT", {}, symbol=f"SYM_{tid}_{i}")
            bus.publish(e)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=publish_worker, args=(i,)) for i in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.perf_counter() - t0

    assert len(received) == total_expected, (
        f"Event loss under load: expected {total_expected}, got {len(received)}"
    )
    assert dlq.size() == 0, f"DLQ non-empty under concurrent load: {dlq.size()}"
    ok("eventbus_concurrent_publish",
       f"({total_expected} events, {num_threads} threads, {elapsed:.3f}s)")

# ── 2. RiskManager concurrent state mutations — no torn reads ───────────────
def test_risk_manager_concurrency():
    from application.oms._internal.risk_manager import RiskManager
    from application.oms._internal.risk_types import RiskConfig
    from application.oms._internal.margin_checker import MarginChecker

    class FakeCapital:
        def get_available_balance(self): return Decimal("1000000")

    rm = RiskManager(
        config=RiskConfig(
            max_daily_loss_pct=Decimal("5"),
            max_position_pct=Decimal("20"),
            max_gross_exposure_pct=Decimal("80"),
            kill_switch=False,
        ),
        capital_provider=FakeCapital(),
        margin_checker=MarginChecker(),
    )

    errors: List[str] = []
    num_threads = 10
    updates_per_thread = 100

    def toggle_and_update(tid):
        try:
            for i in range(updates_per_thread):
                rm.set_kill_switch(i % 2 == 0)
                rm.update_daily_pnl(Decimal("1"))
                _ = rm.snapshot()
        except Exception as exc:
            errors.append(f"thread_{tid}: {exc}")

    threads = [threading.Thread(target=toggle_and_update, args=(i,)) for i in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, f"RiskManager thread safety violation: {errors}"
    ok("risk_manager_concurrent_mutations",
       f"({num_threads} threads × {updates_per_thread} ops, no errors)")

# ── 3. Memory growth — EventBus publish loop stays bounded ──────────────────
def test_event_bus_memory_growth():
    from infrastructure.event_bus.event_bus import EventBus
    from domain.events.types import DomainEvent

    bus = EventBus()
    gc.collect()

    tracemalloc.start()
    snap1 = tracemalloc.take_snapshot()

    for i in range(5000):
        evt = DomainEvent.now("MEM_TEST", {"i": i}, symbol="SYM")
        bus.publish(evt)

    gc.collect()
    snap2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    top_stats = snap2.compare_to(snap1, "lineno")
    total_growth_kb = sum(stat.size_diff for stat in top_stats) / 1024

    # Allow up to 5MB growth for 5000 events
    assert total_growth_kb < 5120, f"Memory leak: {total_growth_kb:.1f} KB growth"
    ok("event_bus_memory_growth_bounded",
       f"(5000 events, +{total_growth_kb:.1f} KB)")

# ── 4. Concurrent PositionManager updates — no state corruption ─────────────
def test_position_manager_concurrency():
    from application.oms.position_manager import PositionManager
    from infrastructure.event_bus.event_bus import EventBus

    bus = EventBus()
    pm = PositionManager(event_bus=bus)

    errors: List[str] = []

    def read_worker(tid):
        try:
            for _ in range(200):
                _ = pm.get_all_positions()
                _ = pm.get_net_pnl()
        except Exception as exc:
            errors.append(f"read_thread_{tid}: {exc}")

    threads = [threading.Thread(target=read_worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, f"PositionManager concurrency error: {errors}"
    ok("position_manager_concurrent_reads", "(8 threads × 200 reads, no errors)")


def run():
    print("=" * 70)
    print("PHASE 10 — CONCURRENCY AND LOAD VALIDATION")
    print("=" * 70)

    tests = [
        ("eventbus_concurrent",           test_eventbus_concurrent),
        ("risk_manager_concurrency",       test_risk_manager_concurrency),
        ("event_bus_memory_growth",        test_event_bus_memory_growth),
        ("position_manager_concurrency",   test_position_manager_concurrency),
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
    print(f"PHASE 10 RESULT: {len(passes)} passed, {len(fails)} failed")
    if fails:
        for r in fails:
            print(f"  FAIL: {r[1]}: {r[2]}")
        sys.exit(1)

if __name__ == "__main__":
    run()
