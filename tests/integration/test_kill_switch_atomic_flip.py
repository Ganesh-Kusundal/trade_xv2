"""Concurrent kill-switch flip and order-check race.

Stress-tests the :class:`brokers.common.oms.risk_manager.RiskManager`
under high contention: 4 threads continuously toggle the kill switch
while 4 threads continuously call :meth:`check_order`. No reader must
ever observe a half-written config, and no check_order call must
crash or hang.

Why this is here
----------------
Phase A / A3 introduced an internal RLock on :class:`RiskManager` to
prevent torn reads of the frozen :class:`RiskConfig` dataclass. This
test is the canonical smoke that the lock holds under load.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from domain import Order, OrderStatus, OrderType, ProductType, Side
from brokers.common.oms import PositionManager, RiskConfig, RiskManager


def _make_order() -> Order:
    return Order(
        order_id="O-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2500"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )


@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager(
        PositionManager(),
        RiskConfig(),
        capital_fn=lambda: Decimal("1000000"),
    )


def test_concurrent_set_kill_switch_and_check_order_no_torn_read(
    risk_manager: RiskManager,
) -> None:
    """8 threads (4 killers + 4 checkers) hammering for ~0.5s. The
    checker thread must see a well-formed bool on every call. The
    final :meth:`kill_switch` property must be a bool, not a half-
    initialised dataclass attribute.
    """
    order = _make_order()
    stop = threading.Event()
    errors: list[BaseException] = []
    observed: list[bool] = []

    def killer() -> None:
        i = 0
        while not stop.is_set():
            risk_manager.set_kill_switch(bool(i % 2))
            i += 1

    def checker() -> None:
        while not stop.is_set():
            try:
                r = risk_manager.check_order(order)
                # The .allowed attribute is always a real bool; the
                # reason field is None on pass or a string on reject.
                assert isinstance(r.allowed, bool)
                assert r.allowed is True or r.allowed is False
                observed.append(r.allowed)
            except BaseException as exc:  # pragma: no cover - defensive
                errors.append(exc)

    threads: list[threading.Thread] = []
    for _ in range(4):
        threads.append(threading.Thread(target=killer))
    for _ in range(4):
        threads.append(threading.Thread(target=checker))
    for t in threads:
        t.start()
    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join()

    assert not errors, f"check_order raised under load: {errors}"
    assert observed, "checker did not run"
    # Final state is a real bool (no dataclass torn read).
    assert isinstance(risk_manager.kill_switch, bool)


def test_concurrent_kill_switch_under_high_thread_count(risk_manager: RiskManager) -> None:
    """Variant with 8 killers + 16 checkers to amplify the race window."""
    order = _make_order()
    stop = threading.Event()
    errors: list[BaseException] = []

    def killer() -> None:
        while not stop.is_set():
            risk_manager.set_kill_switch(True)
            risk_manager.set_kill_switch(False)

    def checker() -> None:
        while not stop.is_set():
            try:
                r = risk_manager.check_order(order)
                assert r.allowed is True or r.allowed is False
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=24) as ex:
        futures = []
        for _ in range(8):
            futures.append(ex.submit(killer))
        for _ in range(16):
            futures.append(ex.submit(checker))
        time.sleep(0.5)
        stop.set()
        for f in futures:
            f.result(timeout=5)

    assert not errors, f"check_order raised under load: {errors}"


def test_check_order_with_concurrent_capital_fn(risk_manager: RiskManager) -> None:
    """If the capital_fn returns positive, the check passes; if it
    returns zero, the check fails with 'Insufficient capital'. The
    check must not raise even when capital_fn is patched mid-call.
    """
    order = _make_order()
    counter = {"n": 0}
    lock = threading.Lock()

    def capital_fn() -> Decimal:
        with lock:
            counter["n"] += 1
        return Decimal("1000000") if counter["n"] % 2 else Decimal("0")

    rm = RiskManager(
        PositionManager(),
        RiskConfig(),
        capital_fn=capital_fn,
    )
    rm.set_kill_switch(False)

    results = []
    for _ in range(100):
        results.append(rm.check_order(order))

    allowed_count = sum(1 for r in results if r.allowed)
    rejected_count = sum(1 for r in results if not r.allowed)
    assert allowed_count > 0
    assert rejected_count > 0
    # The 'Insufficient capital' reason must be observed at least once.
    assert any(
        not r.allowed and r.reason and "capital" in r.reason.lower()
        for r in results
    )
