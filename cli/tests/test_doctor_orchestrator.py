"""Unit tests for CheckOrchestrator.

Tests parallel execution, timeout handling, error recovery, and
result aggregation.

Phase P4-2 (2026-06-22): Orchestrator TDD tests.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from cli.commands.doctor.checks import CheckResult
from cli.commands.doctor.orchestrator import CheckOrchestrator

# ---------------------------------------------------------------------------
# Mock Strategies
# ---------------------------------------------------------------------------


class MockStrategy:
    """Mock strategy for testing."""

    def __init__(self, results: list[CheckResult], delay: float = 0):
        self._results = results
        self._delay = delay
        self.executed = False

    def execute(self, broker_service) -> list[CheckResult]:
        if self._delay > 0:
            time.sleep(self._delay)
        self.executed = True
        return self._results


class FailingStrategy:
    """Strategy that raises an exception."""

    def __init__(self, error_msg: str = "Test error"):
        self._error_msg = error_msg

    def execute(self, broker_service) -> list[CheckResult]:
        raise RuntimeError(self._error_msg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_broker_service():
    """Create a mock broker service."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Test CheckOrchestrator
# ---------------------------------------------------------------------------


class TestCheckOrchestrator:
    """Tests for CheckOrchestrator."""

    def test_run_all_sequential(self, mock_broker_service):
        """Test that all strategies are executed."""
        checks = [
            ("Check1", MockStrategy([CheckResult("Test1", "PASS")])),
            ("Check2", MockStrategy([CheckResult("Test2", "PASS")])),
        ]
        orchestrator = CheckOrchestrator(checks, max_workers=1)
        results = orchestrator.run_all(mock_broker_service)

        assert len(results) == 2
        assert "Check1" in results
        assert "Check2" in results
        assert results["Check1"].results[0].status == "PASS"
        assert results["Check2"].results[0].status == "PASS"

    def test_run_all_parallel(self, mock_broker_service):
        """Test parallel execution with multiple workers."""
        checks = [
            (f"Check{i}", MockStrategy([CheckResult(f"Test{i}", "PASS")], delay=0.1))
            for i in range(4)
        ]
        orchestrator = CheckOrchestrator(checks, max_workers=4)

        start = time.monotonic()
        results = orchestrator.run_all(mock_broker_service)
        elapsed = time.monotonic() - start

        # With 4 workers and 4 checks each taking 0.1s, should complete in ~0.1s
        # (not 0.4s if sequential)
        assert elapsed < 0.3
        assert len(results) == 4

    def test_error_handling(self, mock_broker_service):
        """Test that exceptions are caught and converted to ERROR results."""
        checks = [
            ("Failing", FailingStrategy("Connection lost")),
            ("Passing", MockStrategy([CheckResult("Test", "PASS")])),
        ]
        orchestrator = CheckOrchestrator(checks, max_workers=1)
        results = orchestrator.run_all(mock_broker_service)

        assert "Failing" in results
        assert len(results["Failing"].results) == 1
        assert results["Failing"].results[0].status == "ERROR"
        assert "Connection lost" in results["Failing"].results[0].detail

        # Other checks should still run
        assert "Passing" in results
        assert results["Passing"].results[0].status == "PASS"

    def test_section_result_has_timing(self, mock_broker_service):
        """Test that SectionResult includes execution time."""
        checks = [
            ("Timed", MockStrategy([CheckResult("Test", "PASS")], delay=0.05)),
        ]
        orchestrator = CheckOrchestrator(checks, max_workers=1)
        results = orchestrator.run_all(mock_broker_service)

        assert results["Timed"].elapsed_s >= 0.04

    def test_check_count_property(self):
        """Test check_count returns number of registered checks."""
        checks = [
            ("Check1", MockStrategy([])),
            ("Check2", MockStrategy([])),
            ("Check3", MockStrategy([])),
        ]
        orchestrator = CheckOrchestrator(checks, max_workers=2)

        assert orchestrator.check_count == 3

    def test_empty_checks(self, mock_broker_service):
        """Test orchestrator with no checks."""
        orchestrator = CheckOrchestrator([], max_workers=2)
        results = orchestrator.run_all(mock_broker_service)

        assert len(results) == 0
        assert orchestrator.check_count == 0

    def test_none_broker_service(self):
        """Test orchestrator passes None broker_service correctly."""

        class NoneCheckStrategy:
            def execute(self, broker_service):
                if broker_service is None:
                    return [CheckResult("None Check", "PASS")]
                return [CheckResult("None Check", "FAIL")]

        checks = [("NoneTest", NoneCheckStrategy())]
        orchestrator = CheckOrchestrator(checks, max_workers=1)
        results = orchestrator.run_all(None)

        assert results["NoneTest"].results[0].status == "PASS"

    def test_multiple_results_per_check(self, mock_broker_service):
        """Test that a strategy can return multiple results."""
        checks = [
            (
                "Multi",
                MockStrategy(
                    [
                        CheckResult("Sub1", "PASS"),
                        CheckResult("Sub2", "WARN"),
                        CheckResult("Sub3", "FAIL"),
                    ]
                ),
            ),
        ]
        orchestrator = CheckOrchestrator(checks, max_workers=1)
        results = orchestrator.run_all(mock_broker_service)

        assert len(results["Multi"].results) == 3
