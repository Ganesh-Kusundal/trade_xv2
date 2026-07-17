"""P1-T3 (drift D3): API ``require_live_broker`` enforces the live-order authority.

The dependency previously returned the active broker gateway with no live-order
check, so the API path reached the broker before any gate. It must now call
``authorize_live_order`` and raise 403 on any block (live gate off / flag off /
risk rejected), 503 when the broker service is unavailable.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from interface.api import deps


class _BrokerServiceStub:
    """Real stub for the live broker service.

    Implements only the attributes ``require_live_broker`` reads — no mocking
    of the order/gate/parity logic (test-integrity policy: no mocks on the
    safety path).
    """

    def __init__(self, name, live_actionable, allow_live, active_broker=None):
        self.active_broker_name = name
        self.live_actionable = live_actionable
        self.allow_live_orders = allow_live
        self.active_broker = active_broker


def _patch_broker_service(monkeypatch, svc):
    # Mirror how deps resolves the service at runtime.
    monkeypatch.setattr(deps, "get_broker_service", lambda: svc)


def test_blocks_when_authority_blocks(monkeypatch):
    svc = _BrokerServiceStub("dhan", live_actionable=True, allow_live=False)
    _patch_broker_service(monkeypatch, svc)

    def _auth(**kwargs):
        raise deps.LiveBrokerBlockedError("no live-actionable gate")

    monkeypatch.setattr(deps, "authorize_live_order", _auth)
    with pytest.raises(deps.HTTPException) as exc:
        deps.require_live_broker()
    assert exc.value.status_code == 403


def test_blocks_when_allow_live_off(monkeypatch):
    svc = _BrokerServiceStub("dhan", live_actionable=True, allow_live=False)
    _patch_broker_service(monkeypatch, svc)

    def _auth(**kwargs):
        raise deps.LiveBrokerBlockedError("allow_live_orders disabled")

    monkeypatch.setattr(deps, "authorize_live_order", _auth)
    with pytest.raises(deps.HTTPException) as exc:
        deps.require_live_broker()
    assert exc.value.status_code == 403


def test_passes_when_authorized(monkeypatch):
    svc = _BrokerServiceStub(
        "dhan", live_actionable=True, allow_live=True, active_broker="GATEWAY"
    )
    _patch_broker_service(monkeypatch, svc)

    captured = {}

    def _auth(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(deps, "authorize_live_order", _auth)
    result = deps.require_live_broker()
    assert result == "GATEWAY"
    assert captured["broker"] == "dhan"
    assert captured["allow_live_orders"] is True


def test_503_when_service_unavailable(monkeypatch):
    monkeypatch.setattr(deps, "get_broker_service", lambda: None)
    with pytest.raises(deps.HTTPException) as exc:
        deps.require_live_broker()
    assert exc.value.status_code == 503
