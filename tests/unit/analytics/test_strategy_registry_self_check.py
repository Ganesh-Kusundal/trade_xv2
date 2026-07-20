"""Tests for StrategyRegistry.self_check — golden-bar strategy validation."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.registry import StrategyRegistry, StrategySelfCheckError


class _GoodStrategy:
    name = "good"

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        return Signal(
            symbol=candidate.symbol, signal_type=SignalType.HOLD, confidence=0.0, strategy=self.name
        )


class _RaisingStrategy:
    name = "raises"

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        raise ValueError("broken indicator math")


class _MalformedStrategy:
    name = "malformed"

    def evaluate(self, candidate: Candidate, features: pd.DataFrame):
        return {"not": "a signal"}


def test_self_check_passes_valid_strategy() -> None:
    StrategyRegistry.self_check([_GoodStrategy()])  # must not raise


def test_self_check_raises_on_strategy_exception() -> None:
    with pytest.raises(StrategySelfCheckError, match="broken indicator math"):
        StrategyRegistry.self_check([_RaisingStrategy()])


def test_self_check_raises_on_malformed_return_type() -> None:
    with pytest.raises(StrategySelfCheckError, match="expected Signal"):
        StrategyRegistry.self_check([_MalformedStrategy()])


def test_self_check_passes_registered_builtins() -> None:
    """The strategies StrategyPipeline() defaults to must pass their own self-check."""
    from analytics.strategy.pipeline import BreakoutStrategy, MomentumStrategy

    StrategyRegistry.self_check([MomentumStrategy(), BreakoutStrategy()])


def test_self_check_accepts_custom_candidate_and_features() -> None:
    custom_candidate = Candidate(symbol="CUSTOM", score=Decimal("10"))
    custom_features = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    StrategyRegistry.self_check(
        [_GoodStrategy()], candidate=custom_candidate, features=custom_features
    )


def test_engines_run_self_check_at_construction() -> None:
    """ReplayEngine/PaperTradingEngine must reject a broken strategy at construction, not mid-run."""
    from analytics.replay.engine import ReplayEngine
    from analytics.strategy.pipeline import StrategyPipeline

    with pytest.raises(StrategySelfCheckError):
        ReplayEngine(
            strategy_pipeline=StrategyPipeline(strategies=[_RaisingStrategy()]),
            allow_simulate_without_oms=True,
        )
