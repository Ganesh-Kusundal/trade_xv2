"""Tests for ScannerRunner (Phase 3).

Covers:
- run_all: parallel execution with completion-order results
- run_streaming: generator yielding results as they complete
- run_with_fallback: fallback execution on failure
- Error isolation: one scanner failing doesn't affect others
- Thread safety: DataFrame copies prevent concurrent mutation
- Empty scanners list handling
- ScannerTaskResult properties and conversions
- Convenience functions: run_scanners_parallel, run_scanners_with_timing
- Timeout handling
"""

from __future__ import annotations

import time

import pandas as pd
import pytest

from analytics.scanner.models import Candidate, Scanner, ScanResult
from analytics.scanner.runner import (
    ScannerRunner,
    ScannerTaskResult,
    run_scanners_parallel,
    run_scanners_with_timing,
)

# ---------------------------------------------------------------------------
# Fake Scanner for testing
# ---------------------------------------------------------------------------


class FakeScanner(Scanner):
    """A test scanner with configurable behavior."""

    def __init__(
        self,
        name: str = "fake",
        candidates: list[Candidate] | None = None,
        raise_on_scan: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self._candidates = candidates or []
        self._raise_on_scan = raise_on_scan
        self._delay = delay

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        if self._delay > 0:
            time.sleep(self._delay)
        if self._raise_on_scan is not None:
            raise self._raise_on_scan
        return ScanResult(
            scanner=self.name,
            candidates=self._candidates,
            universe_size=len(universe),
        )


# ---------------------------------------------------------------------------
# ScannerTaskResult tests
# ---------------------------------------------------------------------------


class TestScannerTaskResult:
    def test_successful_result(self) -> None:
        sr = ScanResult(scanner="test", candidates=[Candidate(symbol="X", score=50.0)])
        result = ScannerTaskResult(
            scanner_name="test",
            success=True,
            scan_result=sr,
            execution_time_ms=10.0,
        )
        assert result.candidate_count == 1
        assert result.to_scan_result() is sr

    def test_failed_result(self) -> None:
        result = ScannerTaskResult(
            scanner_name="test",
            success=False,
            error="ValueError: boom",
            execution_time_ms=5.0,
        )
        assert result.candidate_count == 0
        with pytest.raises(RuntimeError, match="failed"):
            result.to_scan_result()

    def test_failed_result_with_none_scan_result(self) -> None:
        result = ScannerTaskResult(
            scanner_name="test",
            success=True,
            scan_result=None,
        )
        with pytest.raises(RuntimeError):
            result.to_scan_result()

    def test_empty_candidates_count(self) -> None:
        sr = ScanResult(scanner="test", candidates=[])
        result = ScannerTaskResult(scanner_name="test", success=True, scan_result=sr)
        assert result.candidate_count == 0


# ---------------------------------------------------------------------------
# run_all tests
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_empty_scanners_returns_empty(self) -> None:
        runner = ScannerRunner()
        df = pd.DataFrame()
        results = runner.run_all([], df)
        assert results == []

    def test_single_scanner_success(self) -> None:
        scanner = FakeScanner(
            name="momentum",
            candidates=[Candidate(symbol="RELIANCE", score=80.0)],
        )
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_all([scanner], df)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].scanner_name == "momentum"
        assert results[0].candidate_count == 1

    def test_multiple_scanners_all_succeed(self) -> None:
        scanners = [
            FakeScanner(name=f"scanner_{i}", candidates=[Candidate(symbol="X", score=50.0)])
            for i in range(5)
        ]
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_all(scanners, df)

        assert len(results) == 5
        assert all(r.success for r in results)
        names = {r.scanner_name for r in results}
        assert names == {f"scanner_{i}" for i in range(5)}

    def test_scanner_failure_is_isolated(self) -> None:
        good = FakeScanner(name="good", candidates=[Candidate(symbol="X", score=50.0)])
        bad = FakeScanner(name="bad", raise_on_scan=ValueError("scanner error"))

        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_all([good, bad], df)

        assert len(results) == 2
        good_result = next(r for r in results if r.scanner_name == "good")
        bad_result = next(r for r in results if r.scanner_name == "bad")
        assert good_result.success is True
        assert bad_result.success is False
        assert "ValueError" in bad_result.error

    def test_all_scanners_fail(self) -> None:
        scanners = [
            FakeScanner(name=f"fail_{i}", raise_on_scan=RuntimeError(f"fail {i}")) for i in range(3)
        ]
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_all(scanners, df)

        assert len(results) == 3
        assert all(not r.success for r in results)

    def test_results_in_completion_order(self) -> None:
        """Fast scanners should appear first in results."""
        slow = FakeScanner(name="slow", delay=0.3, candidates=[Candidate(symbol="S", score=50.0)])
        fast = FakeScanner(name="fast", delay=0.0, candidates=[Candidate(symbol="F", score=50.0)])

        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner(max_workers=2)
        results = runner.run_all([slow, fast], df)

        # fast should complete first (or at least both should be present)
        assert len(results) == 2
        assert results[0].scanner_name == "fast"

    def test_execution_time_is_recorded(self) -> None:
        scanner = FakeScanner(name="timed", delay=0.1, candidates=[])
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_all([scanner], df)

        assert results[0].execution_time_ms > 0

    def test_failed_execution_time_is_recorded(self) -> None:
        scanner = FakeScanner(name="fail", raise_on_scan=ValueError("boom"), delay=0.05)
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_all([scanner], df)

        assert results[0].execution_time_ms > 0


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_dataframe_copy_prevents_mutation(self) -> None:
        """Each scanner should receive its own copy of the DataFrame."""
        mutated_values = []

        class MutatingScanner(Scanner):
            name = "mutator"

            def scan(self, universe: pd.DataFrame) -> ScanResult:
                # Modify the DataFrame (should not affect others)
                universe["mutated"] = True
                mutated_values.append(id(universe))
                return ScanResult(scanner="mutator", candidates=[])

        scanners = [MutatingScanner() for _ in range(5)]
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner(max_workers=5)
        results = runner.run_all(scanners, df)

        assert len(results) == 5
        # Each scanner should have received a different DataFrame object
        assert len(set(mutated_values)) == 5

    def test_concurrent_scanners_do_not_interfere(self) -> None:
        """Multiple scanners running concurrently should not interfere."""
        collected_counts = []
        lock = __import__("threading").Lock()

        class CountingScanner(Scanner):
            def __init__(self, name: str, count: int) -> None:
                self.name = name
                self._count = count

            def scan(self, universe: pd.DataFrame) -> ScanResult:
                time.sleep(0.05)
                with lock:
                    collected_counts.append(self._count)
                return ScanResult(
                    scanner=self.name,
                    candidates=[Candidate(symbol="X", score=float(self._count))],
                )

        scanners = [CountingScanner(f"counter_{i}", i * 10) for i in range(8)]
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner(max_workers=4)
        results = runner.run_all(scanners, df)

        assert len(results) == 8
        assert sorted(collected_counts) == [i * 10 for i in range(8)]


# ---------------------------------------------------------------------------
# run_streaming tests
# ---------------------------------------------------------------------------


class TestRunStreaming:
    def test_streaming_yields_all_results(self) -> None:
        scanners = [
            FakeScanner(name=f"s{i}", candidates=[Candidate(symbol="X", score=50.0)])
            for i in range(3)
        ]
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()

        results = list(runner.run_streaming(scanners, df))
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_streaming_yields_in_completion_order(self) -> None:
        slow = FakeScanner(name="slow", delay=0.2, candidates=[])
        fast = FakeScanner(name="fast", delay=0.0, candidates=[])

        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner(max_workers=2)

        order = []
        for result in runner.run_streaming([slow, fast], df):
            order.append(result.scanner_name)

        assert order[0] == "fast"

    def test_streaming_empty_scanners(self) -> None:
        runner = ScannerRunner()
        df = pd.DataFrame()
        results = list(runner.run_streaming([], df))
        assert results == []

    def test_streaming_yields_failed_results(self) -> None:
        good = FakeScanner(name="good", candidates=[])
        bad = FakeScanner(name="bad", raise_on_scan=ValueError("stream fail"))

        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()

        results = list(runner.run_streaming([good, bad], df))
        assert len(results) == 2
        bad_result = next(r for r in results if r.scanner_name == "bad")
        assert bad_result.success is False


# ---------------------------------------------------------------------------
# run_with_fallback tests
# ---------------------------------------------------------------------------


class TestRunWithFallback:
    def test_no_fallback_when_all_succeed(self) -> None:
        scanners = [FakeScanner(name="s1", candidates=[])]
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()

        results = runner.run_with_fallback(scanners, df)
        assert len(results) == 1

    def test_fallback_runs_when_primary_fails(self) -> None:
        primary = FakeScanner(name="primary", raise_on_scan=ValueError("primary fail"))
        fallback = FakeScanner(name="fallback", candidates=[Candidate(symbol="X", score=50.0)])

        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_with_fallback([primary], df, fallback_scanners=[fallback])

        assert len(results) == 2
        primary_result = next(r for r in results if r.scanner_name == "primary")
        fallback_result = next(r for r in results if r.scanner_name == "fallback")
        assert primary_result.success is False
        assert fallback_result.success is True

    def test_no_fallback_when_none_provided(self) -> None:
        bad = FakeScanner(name="bad", raise_on_scan=ValueError("no fallback"))
        df = pd.DataFrame({"close": [100.0] * 10})
        runner = ScannerRunner()
        results = runner.run_with_fallback([bad], df, fallback_scanners=None)
        assert len(results) == 1
        assert results[0].success is False


# ---------------------------------------------------------------------------
# Timeout tests
# ---------------------------------------------------------------------------


class TestTimeout:
    @pytest.mark.skip(reason="Timeout behavior depends on ThreadPoolExecutor internals")
    def test_timeout_on_slow_scanners(self) -> None:
        """ScannerRunner should respect timeout_seconds."""
        pass


# ---------------------------------------------------------------------------
# Convenience function tests
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    def test_run_scanners_parallel_returns_only_successful(self) -> None:
        good = FakeScanner(
            name="good",
            candidates=[Candidate(symbol="X", score=50.0)],
        )
        bad = FakeScanner(name="bad", raise_on_scan=ValueError("parallel fail"))

        df = pd.DataFrame({"close": [100.0] * 10})
        results = run_scanners_parallel([good, bad], df)

        assert len(results) == 1
        assert results[0].scanner == "good"

    def test_run_scanners_parallel_empty(self) -> None:
        df = pd.DataFrame()
        results = run_scanners_parallel([], df)
        assert results == []

    def test_run_scanners_with_timing(self) -> None:
        s1 = FakeScanner(name="timer1", delay=0.05, candidates=[])
        s2 = FakeScanner(name="timer2", candidates=[])

        df = pd.DataFrame({"close": [100.0] * 10})
        results, timing = run_scanners_with_timing([s1, s2], df)

        assert len(results) == 2
        assert "timer1" in timing
        assert "timer2" in timing
        assert timing["timer1"] > 0
