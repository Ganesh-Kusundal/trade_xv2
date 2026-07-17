"""get_active_session(mode="market") must never touch the full live-trade
bootstrap (OMS/reconciliation/ProductionReadinessChecker) — it should call
BrokerService.market_gateway() instead of active_broker/_ensure_initialized.

Regression coverage for the bug where a read-only feed check discarded an
already-working gateway because an unrelated OMS-readiness check failed
(see interface.ui.services.broker_service._ensure_initialized).
"""

from __future__ import annotations

from application.portfolio.active_session import get_active_session, set_session_opener


class _FakeBrokerService:
    """Records which bootstrap path was used, without any real broker I/O."""

    def __init__(self) -> None:
        self.active_broker_name = "dhan"
        self.market_gateway_calls: list[str] = []
        self.ensure_initialized_calls = 0
        self.active_broker_accessed = False

    def market_gateway(self, name: str):
        self.market_gateway_calls.append(name)
        return object()

    def _ensure_initialized(self) -> None:
        self.ensure_initialized_calls += 1

    @property
    def active_broker(self):
        self.active_broker_accessed = True
        return object()


def _fake_open_session(**kwargs):
    return kwargs


def test_market_mode_uses_market_gateway_not_full_bootstrap():
    set_session_opener(_fake_open_session)
    svc = _FakeBrokerService()

    get_active_session(svc, mode="market")

    assert svc.market_gateway_calls == ["dhan"]
    assert svc.ensure_initialized_calls == 0
    assert svc.active_broker_accessed is False


def test_trade_mode_still_uses_full_bootstrap():
    set_session_opener(_fake_open_session)
    svc = _FakeBrokerService()

    get_active_session(svc, mode="trade")

    assert svc.market_gateway_calls == []
    assert svc.ensure_initialized_calls == 1
    assert svc.active_broker_accessed is True
