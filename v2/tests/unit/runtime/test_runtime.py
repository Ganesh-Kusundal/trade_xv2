"""Runtime layer — comprehensive TDD tests for RuntimeFactory, PluginDiscovery,
ExecutionTargetResolver, Startup, and Runtime dataclass.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.execution.fill_sources import (
    BrokerFillSource,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
)
from application.execution.execution_engine import ExecutionEngine
from application.risk.risk_manager import RiskManager
from config.schema import AppConfig, Environment
from domain.enums import BrokerId
from infrastructure.clock import FakeClock, SystemClock
from infrastructure.component.lifecycle import LifecycleManager
from infrastructure.message_bus import MessageBus
from runtime.discovery import discover_brokers
from runtime.execution_target import resolve_clock, resolve_fill_source
from runtime.factory import RuntimeFactory
from runtime.runtime import Runtime
from runtime.startup import boot
from shared.errors import LifecycleError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(env: Environment = Environment.PAPER) -> AppConfig:
    """Minimal AppConfig for each environment."""
    return AppConfig(environment=env)


def _bare_runtime(*, risk: RiskManager | None = None, env: Environment = Environment.PAPER) -> Runtime:
    """Construct a minimal Runtime for unit tests (no factory wiring)."""
    clock = FakeClock() if env in (Environment.REPLAY, Environment.BACKTEST) else SystemClock()
    fill = resolve_fill_source(env)
    return Runtime(
        bus=MessageBus(),
        cache=MagicMock(),
        execution_engine=MagicMock(),
        risk=risk,
        lifecycle=LifecycleManager(),
        environment=env,
        fill_source=fill,
        clock=clock,
        environment_frozen=False,
    )


# ===========================================================================
# 1. Runtime dataclass contract
# ===========================================================================

class TestRuntimeDataclass:
    def test_dataclass_is_mutable(self) -> None:
        rt = _bare_runtime()
        rt.environment = Environment.LIVE  # type: ignore[misc]
        assert rt.environment is Environment.LIVE

    def test_holds_all_wired_components(self) -> None:
        rt = _bare_runtime()
        assert rt.bus is not None
        assert rt.clock is not None
        assert rt.fill_source is not None
        assert rt.lifecycle is not None
        assert rt.environment is not None


# ===========================================================================
# 2. ExecutionTargetResolver — FillSource + Clock per mode
# ===========================================================================

class TestExecutionTargetResolver:
    """REPLAY/BACKTEST/PAPER/LIVE → (FillSource, Clock) matrix."""

    _MATRIX = [
        (Environment.REPLAY, ReplayFillSource, FakeClock),
        (Environment.BACKTEST, SimulatedFillSource, FakeClock),
        (Environment.PAPER, PaperFillSource, SystemClock),
        (Environment.LIVE, BrokerFillSource, SystemClock),
    ]

    @pytest.mark.parametrize(("env", "fill_cls", "clock_cls"), _MATRIX)
    def test_resolve_fill_source_and_clock(
        self, env: Environment, fill_cls: type, clock_cls: type
    ) -> None:
        fill = resolve_fill_source(env)
        clock = resolve_clock(env)
        assert isinstance(fill, fill_cls), f"{env}: expected {fill_cls.__name__}"
        assert isinstance(clock, clock_cls), f"{env}: expected {clock_cls.__name__}"

    def test_replay_uses_fake_clock(self) -> None:
        clock = resolve_clock(Environment.REPLAY)
        assert isinstance(clock, FakeClock)

    def test_backtest_uses_simulated_fill_source(self) -> None:
        fill = resolve_fill_source(Environment.BACKTEST)
        assert isinstance(fill, SimulatedFillSource)

    def test_paper_uses_system_clock(self) -> None:
        clock = resolve_clock(Environment.PAPER)
        assert isinstance(clock, SystemClock)

    def test_live_uses_system_clock(self) -> None:
        clock = resolve_clock(Environment.LIVE)
        assert isinstance(clock, SystemClock)

    def test_live_broker_fill_source_uses_adapter(self) -> None:
        adapter = MagicMock()
        fill = resolve_fill_source(Environment.LIVE, broker_adapter=adapter)
        assert isinstance(fill, BrokerFillSource)

    def test_paper_uses_gateway_when_provided(self) -> None:
        gateway = MagicMock()
        fill = resolve_fill_source(Environment.PAPER, broker_adapter=gateway)
        assert isinstance(fill, PaperFillSource)

    def test_unsupported_environment_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve_fill_source("INVALID")

    def test_unsupported_environment_clock_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve_clock("INVALID")


# ===========================================================================
# 3. PluginDiscovery — find available brokers
# ===========================================================================

class TestPluginDiscovery:
    def test_discover_finds_all_brokers(self) -> None:
        # Register all known brokers
        from plugins.brokers.dhan import register as register_dhan
        from plugins.brokers.paper import register as register_paper
        from plugins.brokers.upstox import register as register_upstox

        register_dhan()
        register_upstox()
        register_paper()

        found = discover_brokers()
        assert BrokerId.PAPER in found
        assert BrokerId.DHAN in found
        assert BrokerId.UPSTOX in found

    def test_discover_returns_dict_of_broker_ids(self) -> None:
        found = discover_brokers()
        assert isinstance(found, dict)
        for key in found:
            assert isinstance(key, BrokerId)


# ===========================================================================
# 4. RuntimeFactory — build from config
# ===========================================================================

class TestRuntimeFactory:
    def test_build_returns_runtime(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt, Runtime)

    def test_build_wires_execution_engine(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt.execution_engine, ExecutionEngine)

    def test_build_sets_environment(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.BACKTEST))
        assert rt.environment is Environment.BACKTEST

    def test_build_wires_risk_manager(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt.risk, RiskManager)

    def test_build_wires_message_bus(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt.bus, MessageBus)

    def test_build_wires_lifecycle(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt.lifecycle, LifecycleManager)

    def test_build_replay_uses_fake_clock(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.REPLAY))
        assert isinstance(rt.clock, FakeClock)

    def test_build_backtest_uses_simulated_fill_source(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.BACKTEST))
        assert isinstance(rt.fill_source, SimulatedFillSource)

    def test_build_paper_uses_paper_fill_source(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt.fill_source, PaperFillSource)

    def test_build_paper_uses_system_clock(self) -> None:
        rt = RuntimeFactory.build(_cfg(Environment.PAPER))
        assert isinstance(rt.clock, SystemClock)

    def test_all_profiles_build_successfully(self) -> None:
        for env in Environment:
            rt = RuntimeFactory.build(_cfg(env))
            assert rt.environment is env


# ===========================================================================
# 5. Startup — boot checks, environment freeze
# ===========================================================================

class TestStartup:
    def test_boot_freezes_environment(self) -> None:
        rt = _bare_runtime(risk=RiskManager())
        booted = boot(rt)
        assert booted.environment_frozen is True
        # Original unchanged (boot uses dataclasses.replace to copy)
        assert rt.environment_frozen is False

    def test_boot_aborts_without_risk(self) -> None:
        rt = _bare_runtime(risk=None)
        with pytest.raises(LifecycleError, match="risk"):
            boot(rt)

    def test_boot_aborts_when_already_frozen(self) -> None:
        rt = _bare_runtime(risk=RiskManager())
        booted = boot(rt)
        with pytest.raises(LifecycleError, match="already frozen"):
            boot(booted)

    def test_boot_initializes_lifecycle(self) -> None:
        rt = _bare_runtime(risk=RiskManager())
        booted = boot(rt)
        # lifecycle should have been initialized
        assert booted.lifecycle is not None
