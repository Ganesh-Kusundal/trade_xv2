"""Tests for the ReconciliationService (now a ManagedService).

REF: Task 6.3 — Converted from MagicMock to FakeReconciliationService
"""

from __future__ import annotations
from tests.conftest import build_test_trading_context

import time

from application.oms.context import TradingContext
from application.oms.reconciliation_service import ReconciliationService
from domain.events.types import DomainEvent
from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import HealthState, LifecycleManager
from infrastructure.observability.event_metrics import EventMetrics
from tests.fakes import FakeReconciliationService


def _build_ctx() -> tuple[TradingContext, EventBus, EventMetrics]:
    metrics = EventMetrics()
    bus = EventBus(metrics=metrics)
    ctx = build_test_trading_context(event_bus=bus, replay_events=False)
    return ctx, bus, metrics


def test_reconciliation_lifecycle_integration() -> None:
    ctx, bus, _ = _build_ctx()
    # REF: Using FakeReconciliationService instead of _StubReconciliation with MagicMock
    recon = FakeReconciliationService(has_drift=False)
    service = ReconciliationService(
        order_manager=ctx.order_manager,
        position_manager=ctx.position_manager,
        reconciliation_service=recon,
        interval_seconds=0.05,
        event_bus=bus,
    )
    mgr = LifecycleManager()
    mgr.register(service)
    mgr.start_all()
    try:
        time.sleep(0.2)
        assert recon.reconcile_calls >= 1
        assert service.run_count >= 1
    finally:
        mgr.stop_all()
    assert not service.is_alive() if hasattr(service, "is_alive") else True


def test_reconciliation_health_drift_count() -> None:
    ctx, bus, _ = _build_ctx()
    # REF: Using FakeReconciliationService
    recon = FakeReconciliationService(has_drift=True, drift_count=3)
    service = ReconciliationService(
        order_manager=ctx.order_manager,
        position_manager=ctx.position_manager,
        reconciliation_service=recon,
        interval_seconds=3600,  # long; we trigger manually
        event_bus=bus,
    )
    mgr = LifecycleManager()
    mgr.register(service)
    mgr.start_all()
    try:
        report = service.run_now()
        assert report is not None
        assert service.last_drift_count == 3
        snap = mgr.health_snapshot()
        # The service ran but the drift is recorded in metrics/detail.
        assert "oms.reconciliation" in snap
        # The report may have has_drift=True but the service itself is
        # still healthy — drift is data, not service health.
        assert snap["oms.reconciliation"]["state"] == HealthState.HEALTHY.value
    finally:
        mgr.stop_all()


def test_reconciliation_publishes_completed_event() -> None:
    ctx, bus, _ = _build_ctx()
    # REF: Using FakeReconciliationService
    recon = FakeReconciliationService(has_drift=True, drift_count=2)
    service = ReconciliationService(
        order_manager=ctx.order_manager,
        position_manager=ctx.position_manager,
        reconciliation_service=recon,
        interval_seconds=3600,
        event_bus=bus,
    )
    mgr = LifecycleManager()
    mgr.register(service)
    mgr.start_all()
    try:
        seen: list[DomainEvent] = []
        bus.subscribe("RECONCILIATION_COMPLETED", seen.append)
        service.run_now()
        assert len(seen) == 1
        assert seen[0].payload["drift_count"] == 2
    finally:
        mgr.stop_all()


def test_reconciliation_records_error_in_health() -> None:
    ctx, bus, _ = _build_ctx()

    # REF: Using inline fake that raises errors
    class _BoomReconciliation(FakeReconciliationService):
        def reconcile(self, local_orders, local_positions):
            raise RuntimeError("kaboom")

    service = ReconciliationService(
        order_manager=ctx.order_manager,
        position_manager=ctx.position_manager,
        reconciliation_service=_BoomReconciliation(),
        interval_seconds=3600,
        event_bus=bus,
    )
    mgr = LifecycleManager()
    mgr.register(service)
    mgr.start_all()
    try:
        result = service.run_now()
        assert result is None
        # The error is recorded in last_error → DEGRADED state.
        # (Once a subsequent run succeeds, state returns to HEALTHY.)
        snap = mgr.health_snapshot()
        assert snap["oms.reconciliation"]["state"] == HealthState.DEGRADED.value
        assert "kaboom" in snap["oms.reconciliation"]["detail"]
    finally:
        mgr.stop_all()


def test_reconciliation_stop_drains_within_timeout() -> None:
    ctx, bus, _ = _build_ctx()
    # REF: Using FakeReconciliationService
    service = ReconciliationService(
        order_manager=ctx.order_manager,
        position_manager=ctx.position_manager,
        reconciliation_service=FakeReconciliationService(),
        interval_seconds=3600,
        event_bus=bus,
    )
    mgr = LifecycleManager(default_stop_timeout=0.5)
    mgr.register(service)
    mgr.start_all()
    started = time.monotonic()
    mgr.stop_all()
    elapsed = time.monotonic() - started
    assert elapsed < 1.0
