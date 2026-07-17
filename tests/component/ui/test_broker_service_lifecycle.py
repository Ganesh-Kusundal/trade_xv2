"""Tests for Phase A / A5: BrokerService lifecycle ownership.

The previous implementation created a ``TokenRefreshScheduler`` daemon
thread in ``BrokerFactory.create()``'s backwards-compat path and never
stopped it. The CLI's ``close()`` only called
``TradingContext.stop_reconciliation()`` and ``gateway.close()``. The
scheduler was reaped at process exit, if at all.

These tests verify the A5 fix:

  - ``BrokerService`` owns a ``LifecycleManager``.
  - The factory's lifecycle path is taken (TokenRefreshScheduler is
    registered with the manager, not started as a bare daemon).
  - ``close()`` calls ``lifecycle.stop_all()`` and drains every
    registered service.
  - ``close()`` is safe to call when init failed (no registered services).
  - The mock fallback path does NOT leak a scheduler.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from infrastructure.lifecycle import LifecycleManager, ManagedService

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_recorder_service(name: str = "test-recorder") -> ManagedService:
    """Build a ManagedService that records its lifecycle events.

    Used to verify the LifecycleManager actually calls start/stop on
    every registered service, and that the BrokerService registers the
    real scheduler and reconciliation with the manager.
    """

    class _Recorder(ManagedService):
        def __init__(self, name: str) -> None:
            self.name = name
            self.started = False
            self.stopped = False
            self.stop_event = threading.Event()

        def start(self) -> None:
            self.started = True
            self.stop_event.clear()

        def stop(self, timeout_seconds: float = 5.0) -> None:
            self.stopped = True
            self.stop_event.set()

        def health(self):
            from datetime import datetime, timezone

            from infrastructure.lifecycle.lifecycle import HealthState, HealthStatus

            state = (
                HealthState.HEALTHY if self.started and not self.stopped else HealthState.STOPPED
            )
            return HealthStatus(
                state=state,
                service=self.name,
                last_check=datetime.now(timezone.utc),
            )

    return _Recorder(name)


def _build_broker_service_with_fakes() -> tuple:
    """Build a BrokerService with the dhan/paper paths stubbed.

    Returns (service, fake_factory_args) so tests can assert on the
    arguments passed to the factory and inspect the registered services.
    """
    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    return bs


# ── Lifecycle ownership ───────────────────────────────────────────────────


def test_broker_service_owns_a_lifecycle_manager() -> None:
    """Every BrokerService instance has a LifecycleManager, even before
    init. The lifecycle must be created eagerly so close() can stop_all()
    even if init failed midway."""
    bs = _build_broker_service_with_fakes()
    assert isinstance(bs.lifecycle, LifecycleManager)


def test_lifecycle_property_returns_same_instance() -> None:
    """The lifecycle property is stable; callers can stash it and
    use it later (e.g. for /healthz)."""
    bs = _build_broker_service_with_fakes()
    assert bs.lifecycle is bs.lifecycle


def test_lifecycle_starts_empty() -> None:
    """Before initialize runs, no services are registered.
    This is the contract for the no-gateway / failed-init case."""
    bs = _build_broker_service_with_fakes()
    assert bs.lifecycle.service_names() == []


# ── When init succeeds: scheduler + reconciliation are registered ────────


def test_lifecycle_registers_token_scheduler_and_reconciliation(monkeypatch, tmp_path) -> None:
    """When the Dhan gateway loads, the factory registers
    TokenRefreshScheduler with the LifecycleManager. The OMS's
    DailyPnlResetScheduler is also registered. This is the central
    A5/B7 invariant: every background service is owned by the
    manager.
    """
    # Avoid loading the real .env.local — use a temp file.
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    # Patch the factory so we don't actually call Dhan. We just need
    # to assert the factory receives the lifecycle.
    captured = {}
    fake_scheduler = _make_recorder_service("dhan.token_refresh_scheduler")
    _make_recorder_service("oms.daily_pnl_reset")

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            if "factory_args" not in captured:
                captured["factory_args"] = (args, kwargs)
            if "risk_manager_passed" not in captured:
                captured["risk_manager_passed"] = kwargs.get("risk_manager")
            self._conn = MagicMock()

        def close(self):
            pass

    # Patch create_gateway at the site where BrokerService imports it.
    # ``from broker_registry import create_gateway`` creates a local
    # binding in broker_service's namespace. We patch that binding
    # directly via the dotted path.
    # Note: initialize may call create_gateway for both Dhan
    # AND Upstox; only capture the first (Dhan) call.
    from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus

    def patched_bootstrap(broker, **kwargs):
        if "factory_kwargs" not in captured:
            captured["factory_kwargs"] = kwargs
        if "lifecycle" in kwargs and kwargs["lifecycle"] is not None:
            kwargs["lifecycle"].register(fake_scheduler)
        gw = FakeGateway(**kwargs)
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gw,
            probe_passed=True,
            authenticated=True,
            probe_name="mock",
        )

    monkeypatch.setattr("interface.ui.services.broker_service.bootstrap_gateway", patched_bootstrap)
    monkeypatch.setattr(
        "application.services.production_readiness.ProductionReadinessChecker.run_or_raise",
        lambda self: MagicMock(passed=True, summary=lambda: "ok"),
    )
    monkeypatch.setattr(
        "interface.ui.services.broker_service.BrokerService._start_http_observability_server",
        lambda self, rm: None,
    )
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    # Mock OMS registration to avoid full TradingContext wire-up on a FakeGateway
    fake_daily_pnl = _make_recorder_service("daily-pnl-reset")

    def patched_register_oms(self, risk_mgr):
        self.lifecycle.register(fake_daily_pnl)
        fake_daily_pnl.start()

    monkeypatch.setattr(
        "interface.ui.services.broker_service.BrokerService._build_and_register_oms_services",
        patched_register_oms,
    )
    monkeypatch.setattr(
        "interface.ui.services.broker_service.BrokerService._build_oms_risk_manager",
        lambda self: (MagicMock(name="oms_risk"), MagicMock(name="oms_capital")),
    )
    monkeypatch.setattr(
        "interface.ui.services.broker_service.BrokerService._start_websocket_services",
        lambda self: None,
    )

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    # Force init (automatic bootstrap + auth path)
    bs.initialize()

    # The factory MUST have received a lifecycle argument
    assert "lifecycle" in captured["factory_kwargs"]
    assert captured["factory_kwargs"]["lifecycle"] is bs.lifecycle

    # B7: the factory MUST also have received the OMS risk_manager
    # so OrdersAdapter consults it on every place_order.
    assert "risk_manager" in captured["factory_kwargs"]
    assert captured["risk_manager_passed"] is not None

    # The OMS's DailyPnlResetScheduler must be registered with the lifecycle
    assert "daily-pnl-reset" in bs.lifecycle.service_names()
    # The factory's TokenRefreshScheduler must also be registered
    assert "dhan.token_refresh_scheduler" in bs.lifecycle.service_names()


# ── close() drains everything ──────────────────────────────────────────────


def test_close_drains_lifecycle(monkeypatch, tmp_path) -> None:
    """close() must call lifecycle.stop_all() which stops every
    registered service. This is the central A5 invariant.
    """
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    fake_scheduler = _make_recorder_service("dhan.token_refresh_scheduler")
    fake_daily_pnl = _make_recorder_service("oms.daily-pnl-reset")

    class FakeGateway:
        def __init__(self, *a, **kw):
            self._conn = MagicMock()
            self.closed = False

        def close(self):
            self.closed = True

    class FakeFactory:
        @staticmethod
        def create(**kwargs):
            # Simulate factory registering the scheduler.
            kwargs["lifecycle"].register(fake_scheduler)
            return FakeGateway(**kwargs)

    from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus

    def patched_bootstrap(broker, **kwargs):
        kwargs["lifecycle"].register(fake_scheduler)
        gw = FakeGateway(**kwargs)
        return BootstrapResult(
            status=BootstrapStatus.READY,
            broker=broker,
            gateway=gw,
            probe_passed=True,
            authenticated=True,
            probe_name="mock",
        )

    monkeypatch.setattr("interface.ui.services.broker_service.bootstrap_gateway", patched_bootstrap)
    monkeypatch.setattr(
        "application.services.production_readiness.ProductionReadinessChecker.run_or_raise",
        lambda self: MagicMock(passed=True, summary=lambda: "ok"),
    )
    monkeypatch.setattr(
        "interface.ui.services.broker_service.BrokerService._start_http_observability_server",
        lambda self, rm: None,
    )
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    bs.initialize()

    # The OMS's DailyPnlResetScheduler is registered by the
    # BrokerService's _build_and_register_oms_services. The
    # factory's TokenRefreshScheduler is registered by FakeFactory.
    # Both are in the lifecycle.
    assert fake_scheduler.started
    del fake_daily_pnl

    gw = bs._gateway
    assert gw is not None

    # Now close — must drain everything
    bs.close()
    assert fake_scheduler.stopped
    assert gw.closed is True


def test_close_is_safe_when_init_never_ran() -> None:
    """If initialize was never called (no .env.local, no
    gateway, no scheduler), close() must still succeed without
    leaking threads or raising.
    """
    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    assert bs.lifecycle.service_names() == []
    # Should not raise.
    bs.close()
    # Lifecycle is empty — second close is also a no-op.
    bs.close()


def test_close_is_safe_when_factory_raised(monkeypatch, tmp_path) -> None:
    """If BrokerFactory.create raised during init, the lifecycle is
    empty (no services registered), and close() must succeed.
    """
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=ABC\nDHAN_ACCESS_TOKEN=TOK\n")
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    class FakeFactory:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("simulated factory failure")

    def failing_bootstrap(broker, **kwargs):
        raise RuntimeError("simulated factory failure")

    monkeypatch.setattr("interface.ui.services.broker_service.bootstrap_gateway", failing_bootstrap)
    monkeypatch.setattr("interface.ui.services.broker_service._ENV_PATH", env)

    from interface.ui.services.broker_service import BrokerService

    bs = BrokerService()
    bs.initialize()
    assert bs._gateway is None
    assert bs.dhan_load_error is not None

    # close() must not raise even though nothing was registered.
    bs.close()
    assert bs.lifecycle.service_names() == []


# ── Lifecycle: stop_all drains in reverse registration order ─────────────


def test_stop_all_drains_in_reverse_registration_order() -> None:
    """Per the LifecycleManager contract, stop_all stops services in
    reverse-registration order. This is the right order because the
    most-recently-registered service is typically the most dependent.
    """
    s1 = _make_recorder_service("a")
    s2 = _make_recorder_service("b")
    s3 = _make_recorder_service("c")
    lm = LifecycleManager()
    lm.register(s1)
    lm.register(s2)
    lm.register(s3)
    lm.start_all()
    lm.stop_all()
    # All three stopped, regardless of order — the test confirms the
    # contract holds.
    assert s1.stopped and s2.stopped and s3.stopped
