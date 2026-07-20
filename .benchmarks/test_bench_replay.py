"""Benchmarks for replay engine bars/second throughput.

Measures the replay engine's processing speed with the circular
buffer optimization (Phase 3.6).
"""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.pipeline.features import RSI, SMA
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType


class _MockOmsAdapter:
    """Minimal OMS adapter for benchmarking."""

    def open_long(self, symbol, exchange, quantity, price, timestamp, **kw):
        return f"MOCK-{symbol}-BUY-{timestamp}"

    def close_long(self, symbol, exchange, quantity, price, timestamp, **kw):
        return f"MOCK-{symbol}-SELL-{timestamp}"

    def modify_order(self, order_id, **kw):
        return True

    def cancel_order(self, order_id):
        return True

    def get_position(self, symbol, exchange="NSE"):
        return None


class _SimpleRSIStrategy:
    """Minimal RSI strategy for benchmarking."""

    @property
    def name(self) -> str:
        return "bench_rsi"

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        if features.empty:
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
            )
        if "rsi" in features.columns and features["rsi"].iloc[-1] < 30:
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.BUY,
                strategy=self.name,
                confidence=70.0,
                score=70.0,
            )
        return Signal(
            symbol=candidate.symbol, signal_type=SignalType.HOLD, confidence=0.0, strategy=self.name
        )


def _create_strategy():
    from analytics.strategy.pipeline import StrategyPipeline

    return StrategyPipeline(strategies=[_SimpleRSIStrategy()])


@pytest.fixture(scope="module")
def sample_candles() -> pd.DataFrame:
    """Generate realistic candle data for replay benchmarking."""
    n = 5_000
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-02 09:15", periods=n, freq="1min"),
            "symbol": "TESTSYM",
            "open": [100.0 + (i % 375) * 0.01 for i in range(n)],
            "high": [101.0 + (i % 375) * 0.01 for i in range(n)],
            "low": [99.0 + (i % 375) * 0.01 for i in range(n)],
            "close": [100.5 + (i % 375) * 0.01 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )


class TestReplayBenchmarks:
    """Benchmark replay engine throughput."""

    def test_replay_throughput_window_20(self, benchmark, sample_candles: pd.DataFrame) -> None:
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))
        config = ReplayConfig(warmup_bars=50, window_size=20)
        engine = ReplayEngine(pipeline, _create_strategy(), config, oms_adapter=_MockOmsAdapter())
        benchmark(engine.run, sample_candles)

    def test_replay_throughput_window_100(self, benchmark, sample_candles: pd.DataFrame) -> None:
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))
        config = ReplayConfig(warmup_bars=50, window_size=100)
        engine = ReplayEngine(pipeline, _create_strategy(), config, oms_adapter=_MockOmsAdapter())
        benchmark(engine.run, sample_candles)

    def test_replay_throughput_window_500(self, benchmark, sample_candles: pd.DataFrame) -> None:
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))
        config = ReplayConfig(warmup_bars=50, window_size=500)
        engine = ReplayEngine(pipeline, _create_strategy(), config, oms_adapter=_MockOmsAdapter())
        benchmark(engine.run, sample_candles)
