"""
PHASE 9 — FAILURE INJECTION
Tests real error paths: broker rejection, DLQ routing, kill-switch blocking,
duplicate events, concurrent burst, OMS kill-switch enforcement.
"""
import sys
import threading
import traceback
from decimal import Decimal
from typing import List

RESULTS = []

def ok(name):
    RESULTS.append(("PASS", name))
    print(f"  [PASS] {name}")

def fail(name, reason):
    RESULTS.append(("FAIL", name, reason))
    print(f"  [FAIL] {name}: {reason}")

# ── 1. EventBus handler failure → DLQ, not propagation ──────────────────────
def test_handler_failure_dlq():
    from infrastructure.event_bus.event_bus import EventBus
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from domain.events.types import DomainEvent

    dlq = DeadLetterQueue()
    bus = EventBus(dead_letter_queue=dlq)

    def exploding_handler(e):
        raise RuntimeError("handler kaboom")

    bus.subscribe("KABOOM", exploding_handler)
    evt = DomainEvent.now("KABOOM", {"data": 1})
    try:
        bus.publish(evt)   # must NOT raise
        ok("failure_injection — handler exception does not propagate")
    except Exception as exc:
        fail("failure_injection — handler exception does not propagate", str(exc))

    assert dlq.size() >= 1
    ok("failure_injection — failed event in DLQ")

# ── 2. Duplicate event → suppressed ─────────────────────────────────────────
def test_duplicate_event_suppression():
    from infrastructure.event_bus.event_bus import EventBus
    from domain.events.types import DomainEvent

    bus = EventBus()
    seen: List = []
    bus.subscribe("DUP_EVENT", lambda e: seen.append(e))

    evt = DomainEvent.now("DUP_EVENT", {"x": 1})
    bus.publish(evt)
    bus.publish(evt)  # same event_id
    bus.publish(evt)  # same event_id again

    assert len(seen) == 1, f"Duplicate suppression failed: seen={len(seen)}"
    ok("failure_injection — duplicate event_id suppressed")

# ── 3. Kill switch blocks all orders ────────────────────────────────────────
def test_kill_switch_enforcement():
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

    rm.set_kill_switch(True)
    assert rm.is_kill_switch_active() is True

    # check_order must reject when kill switch active
    from domain.orders.requests import OrderRequest
    from domain.enums import OrderSide, OrderType, ProductType
    from domain.value_objects.money import Money
    from domain.value_objects.quantity import Quantity

    req = OrderRequest(
        symbol="MCX:CRUDEOIL26JULFUT",
        exchange="MCX",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        price=Money.of(Decimal("500"), "INR"),
        quantity=Quantity(10),
    )
    result = rm.check_order(req, positions=[])
    assert result.passed is False, "Kill switch did not block order"
    assert "kill" in result.reason.lower() or "switch" in result.reason.lower() or "freeze" in result.reason.lower(), f"Unexpected reason: {result.reason}"
    ok("failure_injection — kill switch blocks order submission")

# ── 4. Multi-symbol burst traffic → no race conditions ──────────────────────
def test_concurrent_event_burst():
    from infrastructure.event_bus.event_bus import EventBus
    from domain.events.types import DomainEvent
    import time

    bus = EventBus()
    lock = threading.Lock()
    events_seen: List = []

    def handler(e):
        with lock:
            events_seen.append(e.symbol)

    bus.subscribe("BURST_EVENT", handler)

    symbols = [f"SYM_{i}" for i in range(10)]
    threads = []
    events_per_symbol = 20

    def publish_burst(sym):
        for _ in range(events_per_symbol):
            e = DomainEvent.now("BURST_EVENT", {}, symbol=sym)
            bus.publish(e)

    t0 = time.perf_counter()
    for sym in symbols:
        t = threading.Thread(target=publish_burst, args=(sym,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    total_expected = len(symbols) * events_per_symbol
    assert len(events_seen) == total_expected, (
        f"Race condition: expected {total_expected} events, got {len(events_seen)}"
    )
    ok(f"failure_injection — concurrent burst: {total_expected} events, no loss, {elapsed:.3f}s")

# ── 5. OMS idempotency — duplicate order ID rejected ────────────────────────
def test_oms_idempotency():
    from application.oms.idempotency_guard import IdempotencyGuard
    import threading

    guard = IdempotencyGuard()
    lock = threading.Lock()
    orders_by_corr = {}

    # First reservation succeeds
    order_id1, early1 = guard.check_and_reserve(lock, orders_by_corr, "CORR-001")
    assert early1 is None, "First reservation should not produce early result"
    assert order_id1 is not None

    # Simulate committed order in book
    from domain.entities.order import Order
    from domain.enums import OrderSide, OrderType, OrderStatus, ProductType
    from domain.value_objects.money import Money
    from domain.value_objects.quantity import Quantity
    order = Order(
        order_id=order_id1,
        correlation_id="CORR-001",
        symbol="MCX:CRUDE",
        exchange="MCX",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        price=Money.of(Decimal("500"), "INR"),
        quantity=Quantity(10),
        status=OrderStatus.OPEN,
    )
    with lock:
        orders_by_corr["CORR-001"] = order

    # Second reservation with same correlation_id returns existing order
    order_id2, early2 = guard.check_and_reserve(lock, orders_by_corr, "CORR-001")
    assert early2 is not None, "Duplicate correlation_id should produce early result"
    ok("failure_injection — OMS idempotency guard blocks duplicate correlation_id")


def run():
    print("=" * 70)
    print("PHASE 9 — FAILURE INJECTION")
    print("=" * 70)

    tests = [
        ("handler_failure_to_dlq",    test_handler_failure_dlq),
        ("duplicate_event_suppression", test_duplicate_event_suppression),
        ("kill_switch_enforcement",    test_kill_switch_enforcement),
        ("concurrent_burst",           test_concurrent_event_burst),
        ("oms_idempotency",            test_oms_idempotency),
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
    print(f"PHASE 9 RESULT: {len(passes)} passed, {len(fails)} failed")
    if fails:
        for r in fails:
            print(f"  FAIL: {r[1]}: {r[2]}")
        sys.exit(1)

if __name__ == "__main__":
    run()
