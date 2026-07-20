"""Integration tests for runtime ExecutionTarget resolver."""

from __future__ import annotations

import pytest
from tests.conftest import build_test_trading_context

from domain.ports.execution_target import ExecutionTarget, ExecutionTargetKind
from runtime.execution_target import resolve_execution_target, resolve_simulated_oms_adapter


@pytest.fixture
def trading_context():
    return build_test_trading_context(replay_events=False)


def test_resolve_paper_target() -> None:
    target = resolve_execution_target(ExecutionTargetKind.PAPER)
    assert isinstance(target, ExecutionTarget)
    assert target.kind is ExecutionTargetKind.PAPER
    assert callable(target.submit_fn())


def test_resolve_replay_and_backtest_share_bt_prefix() -> None:
    replay = resolve_execution_target("replay")
    backtest = resolve_execution_target("backtest")
    assert replay.kind is ExecutionTargetKind.REPLAY
    assert backtest.kind is ExecutionTargetKind.BACKTEST


def test_resolve_live_requires_gateway() -> None:
    with pytest.raises(ValueError, match="gateway"):
        resolve_execution_target(ExecutionTargetKind.LIVE)


def test_resolve_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown execution target"):
        resolve_execution_target("turbo")


def test_resolve_simulated_oms_adapter_paper(trading_context) -> None:
    from application.execution.oms_backtest_adapter import SimulatedOMSAdapter

    adapter = resolve_simulated_oms_adapter("paper", trading_context)
    assert isinstance(adapter, SimulatedOMSAdapter)


def test_resolve_simulated_oms_adapter_live_raises(trading_context) -> None:
    with pytest.raises(ValueError, match="Live mode"):
        resolve_simulated_oms_adapter("live", trading_context)


def test_simulated_oms_adapter_uses_execution_engine(trading_context) -> None:
    from application.execution.execution_engine import ExecutionEngine
    from application.execution.oms_backtest_adapter import SimulatedOMSAdapter, create_execution_adapter

    adapter = create_execution_adapter("replay", trading_context)
    assert isinstance(adapter, SimulatedOMSAdapter)
    assert isinstance(adapter._engine, ExecutionEngine)
    assert adapter._engine.fill_source.kind.value == "replay"


def test_build_execution_engine(trading_context) -> None:
    from application.execution.execution_engine import ExecutionEngine
    from runtime.execution_target import build_execution_engine

    engine = build_execution_engine(trading_context, "backtest")
    assert isinstance(engine, ExecutionEngine)
    assert engine.fill_source.kind.value == "backtest"
