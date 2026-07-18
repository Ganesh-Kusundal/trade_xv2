"""Tests for MultiStrategyRuntime."""

from __future__ import annotations

from runtime.factory import MultiStrategyRuntime, build_multi_strategy_runtime


def test_multi_strategy_runtime_lists_strategy_names():
    runtime = MultiStrategyRuntime(strategy_names=["momentum"])
    assert runtime.list_strategies() == ["momentum"]


def test_build_multi_strategy_runtime_factory():
    runtime = build_multi_strategy_runtime(["momentum"])
    assert runtime.pipeline is not None
    assert runtime.strategies is not None
