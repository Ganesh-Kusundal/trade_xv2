"""Walk-forward engine tests."""

from __future__ import annotations

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from analytics.walk_forward.engine import WalkForwardConfig, WalkForwardEngine


class _HoldStrategy:
    name = "hold"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
        )


def test_walk_forward_window_count() -> None:
    rows = 700
    ts = pd.date_range("2026-01-02 09:15", periods=rows, freq="1min")
    price = 100 + pd.Series(range(rows)).astype(float) * 0.01
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": price,
            "high": price + 0.2,
            "low": price - 0.2,
            "close": price,
            "volume": 5000,
        }
    )

    engine = WalkForwardEngine(
        FeaturePipeline(),
        StrategyPipeline(strategies=[_HoldStrategy()]),
        WalkForwardConfig(train_bars=200, test_bars=50, step_bars=50, initial_capital=50_000),
    )
    result = engine.run(df, symbol="TEST")
    assert result.window_count >= 1
    assert isinstance(result.total_pnl, float)


def test_facade_walk_forward_matches_direct_engine_call() -> None:
    """Analytics.walk_forward() is a thin delegate to WalkForwardEngine (facade parity)."""
    from analytics.facade import Analytics

    rows = 700
    ts = pd.date_range("2026-01-02 09:15", periods=rows, freq="1min")
    price = 100 + pd.Series(range(rows)).astype(float) * 0.01
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": price,
            "high": price + 0.2,
            "low": price - 0.2,
            "close": price,
            "volume": 5000,
        }
    )

    analytics = Analytics()

    # No-args form returns a configurable engine, matching .replay()/.backtest()/.paper().
    engine = analytics.walk_forward(
        strategy_pipeline=StrategyPipeline(strategies=[_HoldStrategy()]),
        config=WalkForwardConfig(
            train_bars=200, test_bars=50, step_bars=50, initial_capital=50_000
        ),
    )
    assert isinstance(engine, WalkForwardEngine)

    # Data form runs and returns a WalkForwardResult.
    result = analytics.walk_forward(
        df,
        symbol="TEST",
        strategy_pipeline=StrategyPipeline(strategies=[_HoldStrategy()]),
        config=WalkForwardConfig(
            train_bars=200, test_bars=50, step_bars=50, initial_capital=50_000
        ),
    )
    assert result.window_count >= 1
    assert isinstance(result.total_pnl, float)
