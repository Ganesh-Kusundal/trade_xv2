"""Failover / chaos-engineering tests.

Three production scenarios are covered:

* ``test_lifecycle_drain_with_stuck_service`` — a service whose
  ``stop()`` blocks forever must NOT prevent ``stop_all`` from
  returning within the per-service timeout. The other services must
  still be drained.

* ``test_dhan_token_refresh_during_in_flight_trade_event`` — a 401
  arriving mid-trade must invoke the token refresh, the trade must
  be processed exactly once, and a second delivery of the same
  trade must be detected as a duplicate.

* ``test_daily_pnl_reset_scheduler_under_clock_skew`` — the IST
  rollover boundary fires exactly once even when the wall clock
  crosses the boundary mid-iteration.

The previous ``tests/chaos/test_failure_modes.py`` covered related
ground; this file is a focused, named-location followup that asserts
on the exact contract: a stuck service can never wedge the lifecycle,
and a token refresh can never cause a trade to be applied twice.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import ClassVar
from unittest.mock import MagicMock, patch

from domain.ports.time_service import use_clock
from domain.ports.time_service_impls import VirtualClock

import pytest

from application.oms import (
    DailyPnlResetScheduler,
    OrderManager,
    OrderRequest,
    PositionManager,
    RiskConfig,
    RiskManager,
)
from domain import (
    OrderStatus,
    Side,
    Trade,
)
from infrastructure.event_bus import DomainEvent, EventBus, EventType
from infrastructure.lifecycle import LifecycleManager
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
    build_health,
)

# ── 1. Lifecycle drain with stuck service ─────────────────────────────────


class _StuckService(ManagedService):
    """A service whose stop() blocks forever."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        self.started = True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        # Block until the test sets the event. Without the lifecycle
        # timeout, this would wedge stop_all.
        self._stop_event.wait()

    def health(self) -> HealthStatus:
        return build_health(self.name, HealthState.HEALTHY, detail="stuck")

    def release(self) -> None:
        self._stop_event.set()


class _QuickService(ManagedService):
    """A service that records its stop() call and returns quickly."""

    instances: ClassVar[list[_QuickService]] = []

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = False
        self.stop_called = False
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self.stop_called = True

    def health(self) -> HealthStatus:
        return build_health(self.name, HealthState.HEALTHY, detail="ok")


def test_lifecycle_drain_with_stuck_service() -> None:
    """Register a stuck service alongside a normal service. The
    lifecycle must honour the per-service timeout and return within
    ~timeout (not hang forever). The normal service is still drained
    (i.e. its ``stop()`` was called).

    Concretely: with a 2-service setup and a 2s default timeout, the
    total elapsed wall time for ``stop_all`` must be < 5s, not 5s+5s
    (which would be a serialised timeout pattern).
    """
    _QuickService.instances = []
    lc = LifecycleManager(default_stop_timeout=2.0)

    stuck = _StuckService(name="stuck")
    quick = _QuickService(name="quick")
    lc.register(stuck)
    lc.register(quick)
    lc.start_all()
    assert stuck.started
    assert quick.started

    t0 = time.monotonic()
    lc.stop_all()
    elapsed = time.monotonic() - t0

    # Per-service timeout is 2s, plus a small buffer for thread start
    # and scheduling. We allow up to 4s for two services in the worst
    # case (serial timeouts).
    assert elapsed < 5.0, f"stop_all took {elapsed:.2f}s — should be < 5s"
    # The normal service was drained despite the stuck one.
    assert quick.stop_called, "quick service was not drained"


def test_lifecycle_drain_with_two_stuck_services_serial_timeout() -> None:
    """Two stuck services with a 2s timeout each: ``stop_all`` must
    return in ~4s (one timeout per stuck service), not hang."""
    lc = LifecycleManager(default_stop_timeout=2.0)
    a = _StuckService("a")
    b = _StuckService("b")
    lc.register(a)
    lc.register(b)
    lc.start_all()

    t0 = time.monotonic()
    lc.stop_all()
    elapsed = time.monotonic() - t0

    # 2 services x 2s timeout = 4s. Allow generous upper bound.
    assert 1.5 < elapsed < 6.0, f"expected ~4s, got {elapsed:.2f}s"
    a.release()
    b.release()


# ── 2. Dhan token refresh during in-flight trade event ───────────────────


def test_dhan_token_refresh_during_in_flight_trade_event() -> None:
    """A 401 arrives mid-trade. The HTTP client refreshes the token
    and the request is retried. The trade event is delivered to the
    OMS exactly once and processed exactly once. A second delivery
    of the same trade (e.g. websocket retry) is rejected as a
    duplicate.
    """
    from brokers.dhan.api.http_client import DhanHttpClient

    # Use a very small retry count to keep the test fast.
    new_token = {"v": "TOK-V1"}
    refresh_calls = {"n": 0}

    def refresh() -> str:
        refresh_calls["n"] += 1
        new_token["v"] = "TOK-V2"
        return "TOK-V2"

    client = DhanHttpClient(
        client_id="X",
        access_token="TOK-V1",
        token_refresh_fn=refresh,
    )
    # Bypass the throttle (default 0.04s for /orders) by patching it.
    client._throttle = lambda *a, **kw: None  # type: ignore[assignment]

    # The 401 is the FIRST response, the 200 is the second.
    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.text = "unauthorized"
    resp_401.json.return_value = {}
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.text = "{}"
    resp_200.json.return_value = {"orderId": "ORD-1", "status": "success"}
    client._session.request = MagicMock(side_effect=[resp_401, resp_200])

    result = client.post("/orders", json={"symbol": "RELIANCE"})
    assert result == {"orderId": "ORD-1", "status": "success"}
    assert refresh_calls["n"] == 1
    assert new_token["v"] == "TOK-V2"
    assert client.access_token == "TOK-V2"

    # The trade event is then processed exactly once. Simulate a
    # second delivery of the same trade.
    from infrastructure.event_bus import ProcessedTradeRepository

    bus = EventBus()
    om = OrderManager(
        event_bus=bus,
        processed_trade_repository=ProcessedTradeRepository(),
    )
    # The OrderManager does NOT auto-subscribe to TRADE on
    # construction — that wiring is done by TradingContext. The
    # caller (the websocket adapter in production) is responsible
    # for hooking on_trade onto the bus. We do the same here.
    bus.subscribe(EventType.TRADE.value, om.on_trade)  # P1-3: Migrated to EventType enum
    order = om.place_order(OrderRequest("RELIANCE", "NSE", Side.BUY, 10, price=Decimal("100")))
    assert order.success
    assert order.order is not None
    trade = Trade(
        trade_id="T-A",
        order_id=order.order.order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    bus.publish(
        DomainEvent.now(EventType.TRADE.value, {"trade": trade}, symbol="RELIANCE")
    )  # P1-3: Migrated to EventType enum
    bus.publish(
        DomainEvent.now(EventType.TRADE.value, {"trade": trade}, symbol="RELIANCE")
    )  # P1-3: Migrated to EventType enum

    # The OMS processed the trade exactly once.
    fresh = om.get_order(order.order.order_id)
    assert fresh is not None
    assert fresh.filled_quantity == 10
    assert fresh.status == OrderStatus.FILLED

    # And the ledger recorded exactly one processed trade.
    repo = om.processed_trade_repository
    assert repo.size() == 1
    # The OMS has its own internal duplicate counter (incremented
    # BEFORE delegating to the repo's mark_processed path, so the
    # ledger's duplicates_observed stays at 0). The contract we care
    # about is: the OMS saw the duplicate and the order book was
    # applied exactly once.
    assert om.trade_recorder.trades_duplicated == 1


def test_dhan_token_refresh_does_not_replay_under_cooldown() -> None:
    """The token refresh has a 60s cooldown. A second 401 arriving
    within the cooldown must NOT trigger another refresh — instead
    the request fails with AuthenticationError. This protects
    against a token-refresh feedback loop.
    """
    from brokers.dhan.api.http_client import _REFRESH_COOLDOWN_SECONDS, DhanHttpClient

    refresh_calls = {"n": 0}

    def refresh() -> str:
        refresh_calls["n"] += 1
        return "TOK-V2"

    client = DhanHttpClient(
        client_id="X",
        access_token="TOK-V1",
        token_refresh_fn=refresh,
    )
    client._throttle = lambda *a, **kw: None  # type: ignore[assignment]

    # First call: 401 then 200.
    resp_401_a = MagicMock(status_code=401, text="nope")
    resp_401_a.json.return_value = {}
    resp_200 = MagicMock(status_code=200, text="{}")
    resp_200.json.return_value = {"ok": 1}
    client._session.request = MagicMock(side_effect=[resp_401_a, resp_200])
    client.get("/positions")
    assert refresh_calls["n"] == 1

    # Second call within the cooldown: 401, no refresh, AuthError.
    resp_401_b = MagicMock(status_code=401, text="nope")
    resp_401_b.json.return_value = {}
    client._session.request = MagicMock(return_value=resp_401_b)
    from brokers.dhan.exceptions import AuthenticationError

    with pytest.raises(AuthenticationError):
        client.get("/positions")
    assert refresh_calls["n"] == 1, "cooldown must suppress the second refresh"

    # Sanity: the cooldown is the documented 60s.
    assert _REFRESH_COOLDOWN_SECONDS == 60


# ── 3. Daily PnL reset scheduler under clock skew ────────────────────────


_IST = timezone(timedelta(hours=5, minutes=30))


def test_daily_pnl_reset_scheduler_under_clock_skew() -> None:
    """Use a fake ``time.time`` to advance the clock across the IST
    midnight boundary. The scheduler must fire the reset exactly
    once, not zero times, and not twice.

    The scheduler computes "last rollover" from the current ``time.time()``
    and compares it to its own ``_last_reset_unix``. We patch
    ``time.time`` (via ``unittest.mock.patch`` on
    ``application.oms.daily_pnl_reset_scheduler._time.time``) to
    return a sequence of timestamps that cross the boundary.
    """
    pm = PositionManager()
    rm = RiskManager(pm, RiskConfig(), capital_fn=lambda: Decimal("100000"))
    s = DailyPnlResetScheduler(rm, poll_interval_seconds=10)

    # Seed a large loss so we can detect whether reset fired.
    rm.update_daily_pnl(Decimal("-5000"))

    # Pretend we last reset at today's IST rollover. That is the
    # canonical "just rolled over, sitting in the new day" state.
    # The scheduler computes ``last_rollover`` as the most recent
    # 00:00 IST at or before ``now``; if that is exactly equal to
    # ``_last_reset_unix`` the boundary has NOT been crossed.
    ist_today_rollover = datetime(2026, 6, 15, 0, 0, tzinfo=_IST)
    s._last_reset_unix = ist_today_rollover.timestamp()

    pre_midnight_utc = datetime(2026, 6, 15, 17, 30, tzinfo=timezone.utc)  # 23:00 IST
    virtual = VirtualClock(initial=pre_midnight_utc)
    with use_clock(virtual):
        s._maybe_reset()
    assert rm.daily_pnl == Decimal("-5000"), "must not fire before boundary"
    assert s._reset_count == 0

    post_midnight_utc = datetime(2026, 6, 15, 18, 31, tzinfo=timezone.utc)  # 00:01 IST
    virtual.set(post_midnight_utc)
    with use_clock(virtual):
        s._maybe_reset()
    assert rm.daily_pnl == Decimal("0"), "must fire after boundary"
    assert s._reset_count == 1

    later = datetime(2026, 6, 15, 19, 30, tzinfo=timezone.utc)  # 01:00 IST
    virtual.set(later)
    with use_clock(virtual):
        s._maybe_reset()
    assert s._reset_count == 1, "must not double-fire within same window"
