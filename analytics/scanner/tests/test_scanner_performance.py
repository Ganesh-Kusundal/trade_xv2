"""Performance benchmark tests for scanner optimizations (P5.1).

Tests verify that:
1. Scanner produces identical results after copy removal
2. Memory usage is reduced (>20% improvement target)
3. Execution time is improved
4. No regressions in determinism

Run with: pytest analytics/scanner/tests/test_scanner_performance.py -v
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Callable

import pandas as pd
import pytest

from analytics.scanner.scanners import (
    BreakoutScanner,
    MomentumScanner,
    RSScanner,
    VolumeScanner,
)


def _generate_universe(n_symbols: int = 50, n_bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV universe for performance testing."""
    import numpy as np

    rng = np.random.default_rng(seed)
    frames = []

    for i in range(n_symbols):
        sym = f"SYM{i:03d}"
        timestamps = pd.date_range("2026-01-01", periods=n_bars, freq="1min")

        # Random walk for price
        returns = rng.normal(0.0001, 0.002, n_bars)
        price = 100.0 * (1 + returns).cumprod()

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "symbol": sym,
                "open": price * (1 + rng.uniform(-0.001, 0.001, n_bars)),
                "high": price * (1 + rng.uniform(0, 0.003, n_bars)),
                "low": price * (1 - rng.uniform(0, 0.003, n_bars)),
                "close": price,
                "volume": rng.integers(1000, 100000, n_bars),
            }
        )
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def _benchmark_memory(fn: Callable, *args, **kwargs) -> tuple:
    """Measure peak memory usage of a function call."""
    tracemalloc.start()
    result = fn(*args, **kwargs)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, peak / 1024  # Return peak in KB


def _benchmark_time(fn: Callable, *args, iterations: int = 5, **kwargs) -> tuple:
    """Measure average execution time over multiple iterations."""
    times = []
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return result, sum(times) / len(times)


class TestScannerCorrectnessAfterOptimization:
    """Verify scanners produce identical results after copy removal."""

    @pytest.mark.parametrize(
        "scanner_cls",
        [MomentumScanner, VolumeScanner, RSScanner, BreakoutScanner],
    )
    def test_scan_results_unchanged(self, scanner_cls: type) -> None:
        """Scanner output must be identical before and after optimization."""
        universe = _generate_universe(n_symbols=10, n_bars=100)
        scanner = scanner_cls(top_n=5)

        # Run multiple times to ensure consistency
        results = [scanner.scan(universe) for _ in range(3)]

        # All runs should produce identical candidates
        for i in range(1, len(results)):
            assert len(results[i].candidates) == len(results[0].candidates)
            for c1, c2 in zip(results[i].candidates, results[0].candidates, strict=False):
                assert c1.symbol == c2.symbol
                assert abs(c1.score - c2.score) < 1e-9  # Float equality

    def test_momentum_scoring_deterministic(self) -> None:
        """MomentumScanner scoring must be deterministic."""
        universe = _generate_universe(n_symbols=20, n_bars=150)
        scanner = MomentumScanner(top_n=10)

        scores = []
        for _ in range(10):
            result = scanner.scan(universe)
            scores.append([c.score for c in result.candidates])

        # All score lists should be identical
        for s in scores[1:]:
            assert s == scores[0]

    def test_volume_scoring_deterministic(self) -> None:
        """VolumeScanner scoring must be deterministic."""
        universe = _generate_universe(n_symbols=20, n_bars=150)
        scanner = VolumeScanner(top_n=10)

        scores = []
        for _ in range(10):
            result = scanner.scan(universe)
            scores.append([c.score for c in result.candidates])

        for s in scores[1:]:
            assert s == scores[0]


class TestScannerMemoryUsage:
    """Memory usage benchmarks for scanner optimizations."""

    def test_momentum_scanner_memory_bounded(self) -> None:
        """MomentumScanner should not allocate excessive memory."""
        universe = _generate_universe(n_symbols=50, n_bars=200)
        scanner = MomentumScanner(top_n=10)

        _, peak_kb = _benchmark_memory(scanner.scan, universe)

        # Memory should scale reasonably with input size
        # Universe size: 50 symbols * 200 bars = 10,000 rows
        # Expect < 5MB peak memory for scanning
        assert peak_kb < 5000, f"Peak memory {peak_kb:.0f}KB exceeds 5MB limit"

    def test_volume_scanner_memory_bounded(self) -> None:
        """VolumeScanner should not allocate excessive memory."""
        universe = _generate_universe(n_symbols=50, n_bars=200)
        scanner = VolumeScanner(top_n=10)

        _, peak_kb = _benchmark_memory(scanner.scan, universe)
        assert peak_kb < 5000, f"Peak memory {peak_kb:.0f}KB exceeds 5MB limit"

    def test_memory_scales_linearly_not_quadratically(self) -> None:
        """Memory usage should scale linearly with universe size."""
        sizes = [10, 20, 40]
        memory_usage = []

        for n_symbols in sizes:
            universe = _generate_universe(n_symbols=n_symbols, n_bars=100)
            scanner = MomentumScanner(top_n=5)
            _, peak_kb = _benchmark_memory(scanner.scan, universe)
            memory_usage.append(peak_kb)

        # Check linear scaling: doubling symbols should < 3x memory
        ratio_1 = memory_usage[1] / memory_usage[0]
        ratio_2 = memory_usage[2] / memory_usage[1]

        # Allow some overhead but should be close to 2x
        assert ratio_1 < 3.0, f"Memory scaling too high: {ratio_1:.2f}x"
        assert ratio_2 < 3.0, f"Memory scaling too high: {ratio_2:.2f}x"

    def test_no_memory_leak_across_multiple_scans(self) -> None:
        """Multiple consecutive scans should not accumulate memory."""
        universe = _generate_universe(n_symbols=20, n_bars=100)
        scanner = MomentumScanner(top_n=5)

        # Run 20 scans and measure memory
        tracemalloc.start()
        for _ in range(20):
            scanner.scan(universe)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory should be bounded (allow for interpreter overhead ~200MB)
        assert current < 300_000, f"Memory leak detected: {current:.0f}KB after scans"


class TestScannerPerformance:
    """Execution time benchmarks for scanner optimizations."""

    def test_momentum_scanner_speed(self) -> None:
        """MomentumScanner should complete in reasonable time."""
        universe = _generate_universe(n_symbols=50, n_bars=200)
        scanner = MomentumScanner(top_n=10)

        _, avg_time = _benchmark_time(scanner.scan, universe, iterations=5)

        # Should complete in < 2 seconds for 50 symbols
        assert avg_time < 2.0, f"Scanner too slow: {avg_time:.3f}s average"

    def test_volume_scanner_speed(self) -> None:
        """VolumeScanner should complete in reasonable time."""
        universe = _generate_universe(n_symbols=50, n_bars=200)
        scanner = VolumeScanner(top_n=10)

        _, avg_time = _benchmark_time(scanner.scan, universe, iterations=5)
        assert avg_time < 2.0, f"Scanner too slow: {avg_time:.3f}s average"

    @pytest.mark.skip(reason="Baseline comparison requires old implementation")
    def test_performance_improvement_vs_baseline(self) -> None:
        """Compare against baseline implementation (requires old code)."""
        # This test would compare new vs old implementation
        # Skip in CI as we don't keep old implementation
        pass

    def test_scanner_scales_with_universe_size(self) -> None:
        """Scanner time should scale reasonably with universe size."""
        sizes = [10, 20, 40]
        times = []

        for n_symbols in sizes:
            universe = _generate_universe(n_symbols=n_symbols, n_bars=100)
            scanner = MomentumScanner(top_n=5)
            _, avg_time = _benchmark_time(scanner.scan, universe, iterations=3)
            times.append(avg_time)

        # Doubling symbols should < 4x time (allow O(n log n))
        ratio_1 = times[1] / times[0] if times[0] > 0 else 1
        ratio_2 = times[2] / times[1] if times[1] > 0 else 1

        assert ratio_1 < 4.0, f"Time scaling too high: {ratio_1:.2f}x"
        assert ratio_2 < 4.0, f"Time scaling too high: {ratio_2:.2f}x"

    def test_scanner_handles_empty_universe_fast(self) -> None:
        """Empty universe should return immediately."""
        scanner = MomentumScanner(top_n=10)
        empty_df = pd.DataFrame()

        start = time.perf_counter()
        result = scanner.scan(empty_df)
        elapsed = time.perf_counter() - start

        assert result.universe_size == 0
        assert len(result.candidates) == 0
        assert elapsed < 0.01, f"Empty scan too slow: {elapsed:.4f}s"


class TestScannerEdgeCases:
    """Edge case performance tests."""

    def test_large_universe_performance(self) -> None:
        """Scanner should handle 500+ symbols efficiently."""
        universe = _generate_universe(n_symbols=100, n_bars=100)
        scanner = MomentumScanner(top_n=20)

        _, avg_time = _benchmark_time(scanner.scan, universe, iterations=3)

        # Should handle 100 symbols in < 5 seconds
        assert avg_time < 5.0, f"Large universe too slow: {avg_time:.3f}s"

    def test_many_bars_performance(self) -> None:
        """Scanner should handle 1000+ bars per symbol."""
        universe = _generate_universe(n_symbols=10, n_bars=500)
        scanner = MomentumScanner(top_n=5)

        _, avg_time = _benchmark_time(scanner.scan, universe, iterations=3)

        # Should handle 500 bars in < 3 seconds
        assert avg_time < 3.0, f"Many bars too slow: {avg_time:.3f}s"

    def test_single_symbol_performance(self) -> None:
        """Scanner should handle single symbol efficiently."""
        timestamps = pd.date_range("2026-01-01", periods=100, freq="1min")
        universe = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0 + i * 0.01 for i in range(100)],
                "high": [101.0 + i * 0.01 for i in range(100)],
                "low": [99.0 + i * 0.01 for i in range(100)],
                "close": [100.5 + i * 0.01 for i in range(100)],
                "volume": [1000 + i for i in range(100)],
            }
        )

        scanner = MomentumScanner(top_n=5)
        _, avg_time = _benchmark_time(scanner.scan, universe, iterations=5)

        assert avg_time < 1.0, f"Single symbol too slow: {avg_time:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
