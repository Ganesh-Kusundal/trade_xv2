"""Architecture ratchet — research modes must not silently claim capital validity."""

from __future__ import annotations

import pytest

from analytics.backtest.engine import BacktestEngine, ResearchMode
from analytics.backtest.fast_backtest import FastBacktestEngine
from analytics.backtest.models import CapitalMetricsLabel
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.strategy.pipeline import StrategyPipeline


def test_backtest_engine_default_is_parity_and_requires_oms() -> None:
    with pytest.raises(ValueError, match="ResearchMode.PARITY requires"):
        BacktestEngine(FeaturePipeline(), StrategyPipeline())


def test_pure_sim_must_be_explicit() -> None:
    engine = BacktestEngine(
        FeaturePipeline(),
        StrategyPipeline(),
        mode=ResearchMode.PURE_SIM,
    )
    assert engine.mode is ResearchMode.PURE_SIM


def test_fast_backtest_result_never_capital_valid() -> None:
    import pandas as pd

    engine = FastBacktestEngine(FeaturePipeline(), StrategyPipeline())
    empty = pd.DataFrame(
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    result = engine.run(empty)
    assert result.capital_metrics_valid is False
    assert result.capital_metrics_label is CapitalMetricsLabel.RESEARCH
    assert result.summary["capital_metrics_valid"] is False


def test_paper_session_builders_are_canonical_parity_entrypoints() -> None:
    import inspect

    from runtime import paper_session

    for name in (
        "build_backtest_engine",
        "build_replay_engine",
        "build_paper_trading_engine",
    ):
        fn = getattr(paper_session, name)
        sig = inspect.signature(fn)
        assert "research_only" in sig.parameters, f"{name} must expose research_only gate"
