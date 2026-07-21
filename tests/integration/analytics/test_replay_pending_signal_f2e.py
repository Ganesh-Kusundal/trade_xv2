"""Regression: pending NEXT_OPEN signals at end-of-run must not crash (F2e)."""

from __future__ import annotations


import pandas as pd
import pytest

from analytics.replay.engine import ReplayEngine
from analytics.replay.models import FillModel, ReplayConfig
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline


class _AlwaysBuy:
    name = "always_buy"

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.BUY,
            confidence=1.0,
            strategy=self.name,
            reasons=["test"],
        )



@pytest.mark.integration
def test_replay_pending_signal_end_of_run_completes() -> None:
    """NEXT_OPEN leaves pending signals; end-of-run cleanup must not AttributeError."""
    n = 25
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="min"),
            "open": [100.0 + i * 0.1 for i in range(n)],
            "high": [101.0 + i * 0.1 for i in range(n)],
            "low": [99.0 + i * 0.1 for i in range(n)],
            "close": [100.5 + i * 0.1 for i in range(n)],
            "volume": [1000] * n,
        },
    )
    config = ReplayConfig(
        initial_capital=100_000.0,
        fill_model=FillModel.NEXT_OPEN,
        warmup_bars=3,
        publish_events=False,
        fail_closed_features=False,
    )
    engine = ReplayEngine(
        strategy_pipeline=StrategyPipeline(strategies=[_AlwaysBuy()]),
        config=config,
        allow_simulate_without_oms=True,
    )
    result = engine.run(df)
    assert result.bars_processed > 0
