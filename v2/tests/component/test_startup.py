"""startup.boot — initialize/start lifecycle; abort when risk unbound."""

from __future__ import annotations

import pytest

from application.execution.fill_sources import SimulatedFillSource
from application.oms import TradingCache
from application.risk import RiskManager
from config.schema import Environment
from infrastructure.clock import FakeClock
from infrastructure.component.lifecycle import LifecycleManager
from infrastructure.message_bus import MessageBus
from runtime.runtime import Runtime
from runtime.startup import boot
from shared.errors import LifecycleError


def _runtime(*, risk: RiskManager | None) -> Runtime:
    return Runtime(
        bus=MessageBus(),
        cache=TradingCache(),
        execution_engine=object(),  # boot does not invoke engine
        risk=risk,
        lifecycle=LifecycleManager(),
        environment=Environment.PAPER,
        fill_source=SimulatedFillSource(),
        clock=FakeClock(),
        environment_frozen=False,
    )


def test_boot_succeeds_and_freezes_environment() -> None:
    rt = _runtime(risk=RiskManager(rules=[]))
    booted = boot(rt)
    assert booted.environment_frozen is True
    assert booted.environment is Environment.PAPER
    assert rt.environment_frozen is False  # original untouched (frozen replace)


def test_boot_aborts_when_risk_missing() -> None:
    rt = _runtime(risk=None)
    with pytest.raises(LifecycleError, match="risk"):
        boot(rt)
