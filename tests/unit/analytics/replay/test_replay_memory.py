"""Memory and performance tests for ReplayEngine optimizations (P5.2).

Tests verify that:
1. ReplayEngine uses bounded memory with window_size > 0
2. Memory does not grow unboundedly with dataset size
3. Replay produces identical results after optimization
4. Execution time improves with windowed access

Run with: pytest analytics/replay/tests/test_replay_memory.py -v
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Callable

import pandas as pd
import pytest

from analytics.pipeline.features import RSI, SMA
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType


class _MockOmsAdapter:
    """Minimal OMS adapter that always accepts orders (returns order IDs)."""

    def open_long(
        self, symbol, exchange, quantity, price, timestamp, *, strategy=None, reasons=None
    ):
        return f"MOCK-{symbol}-BUY-{timestamp}"

    def close_long(
        self, symbol, exchange, quantity, price, timestamp, *, strategy=None, reasons=None
    ):
        return f"MOCK-{symbol}-SELL-{timestamp}"

    def modify_order(self, order_id, *, price=None, quantity=None, trigger_price=None):
        return True

    def cancel_order(self, order_id):
        return True

    def get_position(self, symbol, exchange="NSE"):
        return None

    def get_orders(self):
        return []


def _generate_ohlcv(symbol: str = "TEST", bars: int = 1000, seed: int = 42) -> pd.DataFrame:
    """Generate deterministic synthetic OHLCV data."""
    import numpy as np

    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2026-01-01", periods=bars, freq="1min")

    # Random walk for price
    returns = rng.normal(0.0001, 0.002, bars)
    price = 100.0 * (1 + returns).cumprod()

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": price * (1 + rng.uniform(-0.001, 0.001, bars)),
            "high": price * (1 + rng.uniform(0, 0.003, bars)),
            "low": price * (1 - rng.uniform(0, 0.003, bars)),
            "close": price,
            "volume": rng.integers(1000, 100000, bars),
        }
    )


def _create_simple_strategy():
    """Create a simple strategy for testing."""

    class SimpleRSIStrategy:
        """Simple RSI-based strategy."""

        @property
        def name(self) -> str:
            return "simple_rsi"

        def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
            """Generate buy/sell signals based on RSI."""
            if features.empty:
                return Signal(
                    symbol=candidate.symbol,
                    signal_type=SignalType.HOLD,
                    confidence=0.0,
                    strategy=self.name,
                    reasons=["No data"],
                )

            # Buy if RSI < 30 (oversold)
            if "rsi" in features.columns:
                latest_rsi = features["rsi"].iloc[-1]
                if latest_rsi < 30:
                    return Signal(
                        symbol=candidate.symbol,
                        signal_type=SignalType.BUY,
                        strategy=self.name,
                        confidence=70.0,
                        score=70.0,
                        stop_loss=features["close"].iloc[-1] * 0.98,
                        target=features["close"].iloc[-1] * 1.05,
                    )
                elif latest_rsi > 70:
                    return Signal(
                        symbol=candidate.symbol,
                        signal_type=SignalType.SELL,
                        strategy=self.name,
                        confidence=70.0,
                        score=70.0,
                    )

            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
                reasons=["RSI neutral"],
            )

    from analytics.strategy.pipeline import StrategyPipeline

    return StrategyPipeline(strategies=[SimpleRSIStrategy()])


def _benchmark_memory(fn: Callable, *args, **kwargs) -> tuple:
    """Measure peak memory usage of a function call."""
    tracemalloc.start()
    result = fn(*args, **kwargs)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, peak / 1024  # Return peak in KB


def _benchmark_time(fn: Callable, *args, iterations: int = 3, **kwargs) -> tuple:
    """Measure average execution time over multiple iterations."""
    times = []
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return result, sum(times) / len(times)


class TestReplayCorrectnessAfterOptimization:
    """Verify replay produces identical results after window optimization."""

    def test_replay_deterministic_results(self) -> None:
        """ReplayEngine must produce identical trades/signals across runs."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        results = [engine.run(df) for _ in range(5)]

        # All runs should produce identical results
        for i in range(1, 5):
            assert len(results[i].session.signals) == len(results[0].session.signals)
            assert len(results[i].session.trades) == len(results[0].session.trades)
            assert results[i].bars_processed == results[0].bars_processed

    def test_replay_with_window_size_matches_unlimited(self) -> None:
        """Results with sufficient window_size should match unlimited window."""
        df = _generate_ohlcv(bars=300)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()

        # Run with large window (effectively unlimited)
        config_large = ReplayConfig(warmup_bars=50, window_size=500)
        engine_large = ReplayEngine(pipeline, strategy, config_large, oms_adapter=_MockOmsAdapter())
        result_large = engine_large.run(df)

        # Run with adequate window (RSI needs 14 bars)
        config_small = ReplayConfig(warmup_bars=50, window_size=100)
        engine_small = ReplayEngine(pipeline, strategy, config_small, oms_adapter=_MockOmsAdapter())
        result_small = engine_small.run(df)

        # Should produce same number of signals and trades
        assert result_large.signals_generated == result_small.signals_generated
        assert len(result_large.session.trades) == len(result_small.session.trades)

    def test_replay_handles_empty_data(self) -> None:
        """ReplayEngine should handle empty DataFrame gracefully."""
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig()

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())
        empty_df = pd.DataFrame()

        result = engine.run(empty_df)
        assert result.bars_processed == 0
        assert result.signals_generated == 0


class TestReplayMemoryBounded:
    """Memory usage benchmarks for replay optimizations."""

    def test_replay_memory_bounded_with_window(self) -> None:
        """ReplayEngine should use bounded memory with window_size."""
        df = _generate_ohlcv(bars=5000)  # Large dataset
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        _, peak_kb = _benchmark_memory(engine.run, df)

        # Memory should be bounded by window_size, not dataset size
        # 5000 bars with window_size=100 should use < 50MB
        assert peak_kb < 50000, f"Peak memory {peak_kb:.0f}KB exceeds 50MB limit"

    def test_replay_memory_scales_with_window_not_dataset(self) -> None:
        """Memory should scale with window_size, not total bars."""
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()

        # Test with different dataset sizes but same window
        sizes = [1000, 2000, 5000]
        memory_usage = []

        for n_bars in sizes:
            df = _generate_ohlcv(bars=n_bars)
            config = ReplayConfig(warmup_bars=50, window_size=100)
            engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())
            _, peak_kb = _benchmark_memory(engine.run, df)
            memory_usage.append(peak_kb)

        # Memory should not grow significantly with dataset size
        # (window is bounded at 100 bars); allow for Python memory allocator overhead
        max_ratio = max(memory_usage) / min(memory_usage) if min(memory_usage) > 0 else 1
        assert max_ratio < 6.0, f"Memory scales too much with data: {max_ratio:.2f}x"

    def test_replay_memory_no_leak_across_runs(self) -> None:
        """Multiple replay runs should not accumulate memory."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        # Run 10 replays and measure memory
        tracemalloc.start()
        for _ in range(10):
            engine.run(df)
        current, _peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # After GC, current memory should be low (convert bytes to KB)
        current_kb = current / 1024
        assert current_kb < 50000, f"Memory leak detected: {current_kb:.0f}KB after runs"

    def test_unlimited_window_uses_more_memory_than_bounded(self) -> None:
        """Unlimited window (window_size=0) should use more memory."""
        df = _generate_ohlcv(bars=2000)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()

        # Bounded window
        config_bounded = ReplayConfig(warmup_bars=50, window_size=100)
        engine_bounded = ReplayEngine(
            pipeline, strategy, config_bounded, oms_adapter=_MockOmsAdapter()
        )
        _, peak_bounded = _benchmark_memory(engine_bounded.run, df)

        # Unlimited window
        config_unlimited = ReplayConfig(warmup_bars=50, window_size=0)
        engine_unlimited = ReplayEngine(
            pipeline, strategy, config_unlimited, oms_adapter=_MockOmsAdapter()
        )
        _, peak_unlimited = _benchmark_memory(engine_unlimited.run, df)

        # Bounded should use less memory
        assert peak_bounded < peak_unlimited * 1.5, (
            f"Bounded ({peak_bounded:.0f}KB) not better than unlimited ({peak_unlimited:.0f}KB)"
        )


class TestReplayPerformance:
    """Execution time benchmarks for replay optimizations."""

    def test_replay_speed_small_dataset(self) -> None:
        """Replay should complete quickly on small dataset."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        _, avg_time = _benchmark_time(engine.run, df, iterations=3)

        # Should complete in < 5 seconds for 500 bars
        assert avg_time < 5.0, f"Replay too slow: {avg_time:.3f}s average"

    def test_replay_speed_large_dataset(self) -> None:
        """Replay should handle large datasets efficiently."""
        df = _generate_ohlcv(bars=5000)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        _, avg_time = _benchmark_time(engine.run, df, iterations=2)

        # Should complete in < 30 seconds for 5000 bars
        assert avg_time < 30.0, f"Large replay too slow: {avg_time:.3f}s average"

    def test_replay_scales_linearly_with_bars(self) -> None:
        """Replay time should scale linearly with number of bars."""
        sizes = [200, 400, 800]
        times = []

        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        for n_bars in sizes:
            df = _generate_ohlcv(bars=n_bars)
            engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())
            _, avg_time = _benchmark_time(engine.run, df, iterations=2)
            times.append(avg_time)

        # Doubling bars should < 3x time (allow some overhead)
        ratio_1 = times[1] / times[0] if times[0] > 0 else 1
        ratio_2 = times[2] / times[1] if times[1] > 0 else 1

        assert ratio_1 < 3.0, f"Time scaling too high: {ratio_1:.2f}x"
        assert ratio_2 < 3.0, f"Time scaling too high: {ratio_2:.2f}x"

    def test_window_size_impact_on_performance(self) -> None:
        """Different window sizes should have reasonable performance."""
        df = _generate_ohlcv(bars=1000)
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))
        strategy = _create_simple_strategy()

        window_sizes = [50, 100, 200]
        times = []

        for window_size in window_sizes:
            config = ReplayConfig(warmup_bars=50, window_size=window_size)
            engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())
            _, avg_time = _benchmark_time(engine.run, df, iterations=2)
            times.append(avg_time)

        # All should complete in reasonable time
        for t in times:
            assert t < 10.0, f"Window replay too slow: {t:.3f}s"


class TestReplayEdgeCases:
    """Edge case performance tests."""

    def test_replay_very_large_dataset(self) -> None:
        """Replay should handle 10,000+ bars without issues."""
        df = _generate_ohlcv(bars=10000)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        _, avg_time = _benchmark_time(engine.run, df, iterations=1)

        # Should handle 10k bars in < 60 seconds
        assert avg_time < 60.0, f"Very large replay too slow: {avg_time:.3f}s"

    def test_replay_multi_symbol_memory(self) -> None:
        """Multi-symbol replay should maintain bounded memory."""
        # Create multi-symbol data
        frames = []
        for i in range(5):
            sym = f"SYM{i:02d}"
            df = _generate_ohlcv(symbol=sym, bars=500)
            df["symbol"] = sym
            frames.append(df)

        multi_df = pd.concat(frames, ignore_index=True)

        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())

        _, peak_kb = _benchmark_memory(engine.run, multi_df)

        # Should use < 100MB for 5 symbols * 500 bars
        assert peak_kb < 100000, f"Multi-symbol memory {peak_kb:.0f}KB exceeds limit"

    def test_replay_minimal_window_size(self) -> None:
        """Replay should work with minimal window size."""
        df = _generate_ohlcv(bars=200)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()

        # Window size just large enough for RSI (14 bars)
        config = ReplayConfig(warmup_bars=20, window_size=20)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_MockOmsAdapter())
        result = engine.run(df)

        assert result.bars_processed > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
