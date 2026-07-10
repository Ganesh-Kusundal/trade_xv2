"""Tests for MultiStrategyRuntime."""

from __future__ import annotations

from analytics.strategy.registry import StrategyRegistry
from application.trading.multi_strategy_runtime import MultiStrategyRuntime


def test_multi_strategy_runtime_lists_builtin_strategies():
    StrategyRegistry.discover("analytics.strategy.builtins")
    runtime = MultiStrategyRuntime(strategy_names=["momentum"])
    assert runtime.list_strategies() == ["momentum"]
    assert runtime.pipeline is not None


def test_create_pipeline_factory():
    StrategyRegistry.discover("analytics.strategy.builtins")
    pipeline = MultiStrategyRuntime.create_pipeline(["momentum"])
    assert pipeline is not None
