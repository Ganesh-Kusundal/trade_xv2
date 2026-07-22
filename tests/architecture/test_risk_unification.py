"""ADR-0017/0018 — RiskManager uses RiskGate and a single domain KillSwitch."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_risk_manager_delegates_exposure_to_risk_gate():
    from application.oms._internal import risk_manager

    src = inspect.getsource(risk_manager.RiskManager._check_exposure_limits)
    assert "_risk_gate.evaluate" in src or "_risk_gate.check_order" in src


@pytest.mark.architecture
def test_risk_manager_instantiates_domain_kill_switch():
    from application.oms._internal import risk_manager

    src = inspect.getsource(risk_manager.RiskManager.__init__)
    assert "DomainKillSwitch" in src
    assert "domain_kill_switch is None" in src
