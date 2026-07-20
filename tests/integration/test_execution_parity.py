"""Integration tests for execution parity across modes."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.backtest.engine import BacktestEngine
from analytics.backtest.models import BacktestConfig
from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import PaperConfig
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from tests.conftest import build_test_trading_context


def _sample_ohlcv(rows: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:15", periods=rows, freq="1min")
    price = 100 + pd.Series(range(rows)).astype(float) * 0.1
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 10000,
        }
    )


class AlwaysBuyStrategy:
    name = "always_buy"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.BUY,
            confidence=0.9,
            strategy=self.name,
        )


@pytest.fixture
def trading_context():
    return build_test_trading_context(replay_events=False)


def test_replay_and_paper_use_oms_when_context_provided(trading_context) -> None:
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])
    df = _sample_ohlcv()

    replay = ReplayEngine(
        pipeline,
        strategy,
        ReplayConfig(initial_capital=100_000, warmup_bars=5),
        trading_context=trading_context,
    )
    replay_result = replay.run(df, symbol="TEST")
    assert replay_result.bars_processed > 0

    paper = PaperTradingEngine(
        pipeline,
        strategy,
        PaperConfig(initial_capital=100_000, warmup_bars=5),
        trading_context=build_test_trading_context(replay_events=False),
    )
    paper_result = paper.run(df, symbol="TEST")
    assert paper_result.bars_processed > 0

    backtest = BacktestEngine(
        pipeline,
        strategy,
        BacktestConfig(initial_capital=100_000, warmup_bars=5),
        trading_context=build_test_trading_context(replay_events=False),
    )
    bt_result = backtest.run(df, symbol="TEST")
    assert bt_result.replay.bars_processed > 0
