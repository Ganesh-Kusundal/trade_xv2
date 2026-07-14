"""Golden-bar StrategyRegistry.self_check — fail-loud at engine construction."""

from __future__ import annotations

import pytest

from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import MomentumStrategy, StrategyPipeline
from analytics.strategy.registry import StrategyRegistry, StrategySelfCheckError


class _BrokenStrategy:
    name = "broken"

    def evaluate(self, candidate, features):
        raise RuntimeError("deliberately broken")


class _WrongReturnTypeStrategy:
    name = "wrong_return"

    def evaluate(self, candidate, features):
        return "not-a-signal"


class _ValidHoldStrategy:
    name = "valid_hold"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
        )


def test_self_check_passes_for_valid_strategy() -> None:
    StrategyRegistry.self_check([_ValidHoldStrategy(), MomentumStrategy()])


def test_self_check_raises_when_strategy_raises() -> None:
    with pytest.raises(StrategySelfCheckError, match="broken"):
        StrategyRegistry.self_check([_BrokenStrategy()])


def test_self_check_raises_on_non_signal_return() -> None:
    with pytest.raises(StrategySelfCheckError, match="wrong_return"):
        StrategyRegistry.self_check([_WrongReturnTypeStrategy()])


def test_replay_engine_construction_runs_self_check() -> None:
    """ReplayEngine construction must fail loud on a broken strategy."""
    from analytics.pipeline.pipeline import FeaturePipeline
    from analytics.replay.engine import ReplayEngine

    with pytest.raises(StrategySelfCheckError, match="broken"):
        ReplayEngine(
            FeaturePipeline(),
            StrategyPipeline(strategies=[_BrokenStrategy()]),
            allow_simulate_without_oms=True,
        )


def test_paper_engine_construction_runs_self_check() -> None:
    from analytics.paper.engine import PaperTradingEngine
    from analytics.pipeline.pipeline import FeaturePipeline
    from tests.conftest import build_test_trading_context

    with pytest.raises(StrategySelfCheckError, match="broken"):
        PaperTradingEngine(
            FeaturePipeline(),
            StrategyPipeline(strategies=[_BrokenStrategy()]),
            trading_context=build_test_trading_context(replay_events=False),
        )
