"""Regression tests for REF-1: post-construction reconciliation attach.

Historically, ``TradingContext.attach_reconciliation_service`` was *called* by
the OMS bootstrap (oms_bootstrap.py:190,204) but never *implemented*. The call
was swallowed by a bare ``except Exception`` that only logged, so broker
reconciliation silently never attached on that path — the local OMS book never
healed against broker truth.

These tests assert the method exists, wires the reconciler (placement gate +
hot-path event subscriptions + lifecycle registration + immediate run), is
idempotent on re-attach, and that the bootstrap wrapper re-raises for LIVE
brokers instead of swallowing the failure.
"""

from __future__ import annotations

from typing import Any

import pytest

from application.oms.context import TradingContext
from domain.events.types import DomainEvent, EventType
from infrastructure.lifecycle import LifecycleManager
from tests.conftest import build_test_trading_context


class StubReconciliationService:
    """Minimal IReconciliationService used to assert wiring without a broker SDK."""

    def __init__(self) -> None:
        self.requested = False
        self.ran_now = False

    def reconcile(self, local_orders=None, local_positions=None):
        return None

    def request_reconciliation(self, *args: Any, **kwargs: Any) -> None:
        self.requested = True

    def run_now(self) -> None:
        self.ran_now = True

    def stop(self) -> None:
        pass


class _LifecycleSpy(LifecycleManager):
    """LifecycleManager that records registrations."""

    def __init__(self) -> None:
        super().__init__()
        self.registered: list[Any] = []

    def register(self, service: Any) -> None:  # type: ignore[override]
        self.registered.append(service)
        super().register(service)


def _build_ctx() -> TradingContext:
    """A live-shaped context WITHOUT reconciliation via __init__."""
    ctx = build_test_trading_context()
    assert ctx._reconciliation_service is None
    return ctx


def _trade_applied() -> DomainEvent:
    return DomainEvent.now(EventType.TRADE_APPLIED.value, {})


def _order_updated() -> DomainEvent:
    return DomainEvent.now(EventType.ORDER_UPDATED.value, {})


def test_attach_wires_reconciler_and_gate() -> None:
    ctx = _build_ctx()
    lifecycle = _LifecycleSpy()
    ctx.attach_lifecycle(lifecycle)

    stub = StubReconciliationService()
    ctx.attach_reconciliation_service(stub, lifecycle=lifecycle)

    assert ctx._reconciliation_service is not None
    # The wrapper ReconciliationService (not the raw stub) is registered.
    assert ctx._reconciliation_service in lifecycle.registered
    # Placement gate must be engaged: orders gated until first clean recon.
    assert ctx._reconciliation_ready is False
    ctx.stop_reconciliation()


def test_attach_subscribes_hot_path_events() -> None:
    ctx = _build_ctx()
    stub = StubReconciliationService()
    ctx.attach_reconciliation_service(stub)

    # Emitting an order lifecycle event must wake the reconciliation loop.
    ctx._event_bus.publish(_trade_applied())
    assert ctx._reconciliation_service._immediate_request.is_set(), (
        "TRADE_APPLIED should trigger request_reconciliation"
    )
    ctx.stop_reconciliation()


def test_attach_is_idempotent_replace() -> None:
    ctx = _build_ctx()
    first = StubReconciliationService()
    second = StubReconciliationService()
    ctx.attach_reconciliation_service(first)
    wrapper1 = ctx._reconciliation_service
    ctx.attach_reconciliation_service(second)
    wrapper2 = ctx._reconciliation_service

    # A distinct wrapper is installed and the prior one is stopped.
    assert wrapper1 is not wrapper2
    assert wrapper1._stop_event.is_set(), "old reconciler must be stopped"
    # The new wrapper is the one wired to the hot path.
    ctx._event_bus.publish(_order_updated())
    assert wrapper2._immediate_request.is_set()
    ctx.stop_reconciliation()


def test_attach_runs_immediately_via_lifecycle(monkeypatch) -> None:
    ctx = _build_ctx()
    lifecycle = _LifecycleSpy()
    ctx.attach_lifecycle(lifecycle)
    stub = StubReconciliationService()
    # Force startup reconciliation to actually run (CI may set the skip flag).
    monkeypatch.setenv("TRADEX_SKIP_STARTUP_RECONCILIATION", "0")
    ctx.attach_reconciliation_service(stub, lifecycle=lifecycle)
    # run_now() is invoked on the wrapper ReconciliationService (which delegates
    # to the stub's reconcile()), incrementing its run_count.
    assert ctx._reconciliation_service.run_count > 0, (
        "reconciliation must run_now() when a lifecycle is supplied"
    )
    ctx.stop_reconciliation()


def test_bootstrap_reraises_for_live_broker(monkeypatch) -> None:
    """oms_bootstrap must NOT swallow a live-broker attach failure."""
    from interface.ui.services import oms_bootstrap

    ctx = _build_ctx()

    class _Conn:
        orders = object()
        portfolio = object()

    class _Svc:
        _trading_context = ctx
        _live_actionable = True  # LIVE broker
        _lifecycle = None
        _gateway = type("G", (), {"_conn": _Conn()})()
        _upstox_gateway = None

    boot = oms_bootstrap.OmsBootstrap(_Svc())  # type: ignore[arg-type]

    _orig = oms_bootstrap.get_dhan_reconciliation_service_factory

    def _boom(*a: Any, **k: Any):
        raise RuntimeError("recon adapter exploded")

    monkeypatch.setattr(oms_bootstrap, "get_dhan_reconciliation_service_factory", _boom)
    try:
        with pytest.raises(RuntimeError):
            boot._attach_broker_reconciliation(_Svc())  # type: ignore[arg-type]
    finally:
        monkeypatch.setattr(oms_bootstrap, "get_dhan_reconciliation_service_factory", _orig)
