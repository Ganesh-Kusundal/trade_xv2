"""End-to-end regression tests for the OMS path.

This file is the canonical home for "would a real production failure
slip through?" tests. Each test maps to a named incident or to an
invariant the production certification report explicitly called out
(DH-906, kill switch, trade idempotency, lifecycle drain order).

Tests:

* ``test_place_order_kill_switch_under_contention`` — 4 threads
  attempt ``place_order`` concurrently while the kill switch is on.
  All 4 must be rejected with the canonical reason.

* ``test_dhan_place_order_with_read_cb_open_still_posts_order`` —
  direct regression for DH-906: an OPEN read circuit breaker must
  not block ``POST /orders``. The CB split (Phase A / A1) was the
  fix; this test pins the invariant.

* ``test_record_trade_unknown_order_does_not_mark_ledger`` — a
  trade for an unknown order must return False and must NOT mark
  the ledger, so a later ORDER_UPDATED delivery can retry it.
  Calling ``record_trade`` with the same trade a second time must
  still return False (the ledger is not poisoned on first sight).

* ``test_oms_drains_in_reverse_registration_order`` — a lifecycle
  with 3 services must stop them in reverse-registration order.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

from brokers.common.core.domain import (
    Side,
    Trade,
)
from brokers.common.event_bus import EventBus, ProcessedTradeRepository, TradeIdKey
from brokers.common.lifecycle import (
    HealthState,
    HealthStatus,
    LifecycleManager,
    ManagedService,
    build_health,
)
from brokers.common.oms import (
    OrderManager,
    OrderRequest,
    PositionManager,
    RiskConfig,
    RiskManager,
)
from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)

# ── 1. Place-order with kill-switch under contention ─────────────────────


def test_place_order_kill_switch_under_contention() -> None:
    """4 threads call place_order concurrently while the kill switch
    is on. Every call must be rejected with the canonical kill-
    switch reason. No order may be admitted.
    """
    pm = PositionManager()
    rm = RiskManager(pm, RiskConfig(), capital_fn=lambda: Decimal("100000"))
    rm.set_kill_switch(True)

    bus = EventBus()
    om = OrderManager(event_bus=bus, risk_manager=rm)

    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 10, price=Decimal("100"))
    barrier = threading.Barrier(4)

    def attempt(_i: int) -> bool:
        barrier.wait()  # align the threads
        result = om.place_order(req)
        return result.success

    with ThreadPoolExecutor(max_workers=4) as ex:
        successes = list(ex.map(attempt, range(4)))

    assert all(s is False for s in successes), (
        f"some threads admitted orders despite kill switch: {successes}"
    )

    # No order was admitted.
    assert om.get_orders() == []
    # And the kill switch is still on.
    assert rm.kill_switch is True


# ── 2. DH-906 regression: open read CB must not block writes ──────────────


def test_dhan_place_order_with_read_cb_open_still_posts_order() -> None:
    """A read CB that is OPEN must NOT block a POST /orders call.

    The original DH-906 incident was caused by a single
    ``CircuitBreaker("dhan-api")`` being used for every endpoint; a
    storm of failed option-chain reads opened the breaker and the
    order placement was blocked. Phase A / A1 split the breaker into
    read / write / admin categories. This test pins that split.
    """
    from brokers.dhan.exceptions import DhanError
    from brokers.dhan.http_client import DhanHttpClient

    cb_read = CircuitBreaker(
        "test-read", CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000)
    )
    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=10, open_duration_ms=30_000)
    )
    client = DhanHttpClient(
        client_id="X", access_token="T",
        read_circuit_breaker=cb_read, write_circuit_breaker=cb_write,
    )
    # Bypass throttle to keep the test fast.
    client._throttle = lambda *a, **kw: None  # type: ignore[assignment]

    # Drive the read CB past its threshold with one failed read.
    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.text = "boom"
    client._session.request = MagicMock(return_value=resp_503)
    with pytest.raises(DhanError):
        client.get("/marketfeed/quote")
    assert cb_read.state == CircuitState.OPEN

    # Now attempt a POST /orders. The read CB is OPEN, the write CB
    # is CLOSED — the request must NOT be blocked. We stub a 200
    # response.
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.text = "{}"
    resp_200.json.return_value = {"orderId": "ORD-1", "status": "success"}
    client._session.request = MagicMock(return_value=resp_200)

    # The call must succeed.
    result = client.post("/orders", json={"symbol": "RELIANCE"})
    assert result == {"orderId": "ORD-1", "status": "success"}
    # The write CB was never opened.
    assert cb_write.state == CircuitState.CLOSED


def test_dhan_post_orders_with_write_cb_open_fails_fast() -> None:
    """The inverse: a write CB that is OPEN must fast-fail a
    POST /orders call. The split is symmetrical: read-failures do
    not block writes, but write-failures DO block writes.
    """
    from brokers.dhan.exceptions import DhanError
    from brokers.dhan.http_client import DhanHttpClient

    cb_write = CircuitBreaker(
        "test-write", CircuitBreakerConfig(failure_threshold=1, open_duration_ms=30_000)
    )
    client = DhanHttpClient(
        client_id="X", access_token="T",
        write_circuit_breaker=cb_write,
    )
    client._throttle = lambda *a, **kw: None  # type: ignore[assignment]

    # Trip the write CB with one failed POST.
    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.text = "boom"
    client._session.request = MagicMock(return_value=resp_503)
    with pytest.raises(DhanError):
        client.post("/orders", json={"symbol": "X"})
    assert cb_write.state == CircuitState.OPEN

    # A second POST must fast-fail. We do NOT stub a 200 — the
    # circuit breaker must block the request before any HTTP call.
    client._session.request = MagicMock(
        side_effect=AssertionError("session.request should NOT be called when CB is OPEN")
    )
    with pytest.raises(DhanError, match="Circuit breaker open"):
        client.post("/orders", json={"symbol": "X"})


# ── 3. record_trade with unknown order does not mark ledger ──────────────


def test_record_trade_unknown_order_does_not_mark_ledger() -> None:
    """A trade whose ``order_id`` is not yet in the OMS must return
    False. The processed-trade ledger must NOT be marked, so a
    later ORDER_UPDATED delivery can retry processing the trade.

    Calling ``record_trade`` a second time with the same trade
    must STILL return False (no ledger entry, no double-counting).
    """
    bus = EventBus()
    ledger = ProcessedTradeRepository()
    om = OrderManager(event_bus=bus, processed_trade_repository=ledger)

    trade = Trade(
        trade_id="T-UNKNOWN",
        order_id="OM-DOES-NOT-EXIST",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )

    # First call: returns False (order unknown), ledger NOT marked.
    assert om.record_trade(trade) is False
    key = TradeIdKey.from_trade(trade)
    assert not ledger.is_processed(key), (
        "ledger must not be marked when order is unknown"
    )
    assert ledger.size() == 0

    # Second call with the same trade: still False, still not marked.
    assert om.record_trade(trade) is False
    assert not ledger.is_processed(key)
    assert ledger.size() == 0

    # Now place the order, then re-attempt the trade. It must
    # succeed and the ledger must be marked exactly once.
    result = om.place_order(
        OrderRequest("RELIANCE", "NSE", Side.BUY, 10, price=Decimal("100"))
    )
    assert result.success and result.order is not None
    # Re-create the trade with the now-known order_id.
    new_trade = Trade(
        trade_id="T-UNKNOWN",
        order_id=result.order.order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    assert om.record_trade(new_trade) is True
    assert ledger.is_processed(TradeIdKey.from_trade(new_trade))
    assert ledger.size() == 1


def test_record_trade_known_order_dedupes_on_second_call() -> None:
    """Sanity counterpart: a known order, the same trade arrives
    twice. First call returns True, second call returns False and
    the order is not double-filled.
    """
    bus = EventBus()
    ledger = ProcessedTradeRepository()
    om = OrderManager(event_bus=bus, processed_trade_repository=ledger)

    result = om.place_order(
        OrderRequest("RELIANCE", "NSE", Side.BUY, 10, price=Decimal("100"))
    )
    assert result.success and result.order is not None
    trade = Trade(
        trade_id="T-KNOWN",
        order_id=result.order.order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )

    assert om.record_trade(trade) is True
    assert om.record_trade(trade) is False
    fresh = om.get_order(result.order.order_id)
    assert fresh is not None
    assert fresh.filled_quantity == 10


# ── 4. Lifecycle drains in reverse-registration order ───────────────────


class _StopOrderRecorder(ManagedService):
    """Records the order in which its ``stop()`` is called."""

    instances: ClassVar[list[_StopOrderRecorder]] = []

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = False
        self.stopped_at: float | None = None
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self.stopped_at = time.monotonic()

    def health(self) -> HealthStatus:
        return build_health(self.name, HealthState.HEALTHY, detail="ok")


def test_oms_drains_in_reverse_registration_order() -> None:
    """Register 3 services in order A, B, C. ``stop_all`` must call
    ``stop()`` on C first, then B, then A.
    """
    _StopOrderRecorder.instances = []
    lc = LifecycleManager()
    a = _StopOrderRecorder("a")
    b = _StopOrderRecorder("b")
    c = _StopOrderRecorder("c")
    lc.register(a)
    lc.register(b)
    lc.register(c)
    lc.start_all()
    assert all(s.started for s in (a, b, c))

    # Stagger the stop times to make ordering observable in the
    # ``stopped_at`` field.
    def slow_stop(self, timeout_seconds: float = 5.0) -> None:
        self.stopped_at = time.monotonic()
        # Sleep so a different stopping service has a strictly
        # later timestamp. Use small per-service delay based on name
        # to disambiguate.
        if self.name == "c":
            time.sleep(0.05)
        elif self.name == "b":
            time.sleep(0.10)
        # 'a' sleeps longest so its stopped_at is the latest.
        else:
            time.sleep(0.15)

    for s in (a, b, c):
        s.stop = slow_stop.__get__(s)

    t0 = time.monotonic()
    lc.stop_all()
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"stop_all took {elapsed:.2f}s — should be < 2s"

    # C stopped first (smallest stopped_at), then B, then A.
    assert a.stopped_at is not None
    assert b.stopped_at is not None
    assert c.stopped_at is not None
    assert c.stopped_at < b.stopped_at < a.stopped_at, (
        f"stop order: a={a.stopped_at}, b={b.stopped_at}, c={c.stopped_at} — "
        "expected c < b < a (reverse-registration)"
    )
