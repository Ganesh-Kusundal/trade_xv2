"""Golden dataset regression tests — detect behavioral drift.

These tests replay historical sessions and compare results against
saved golden datasets to ensure refactoring doesn't change behavior.

Run with:
    pytest tests/architecture/regression_invariants/test_golden_dataset.py -v
    pytest tests/architecture/regression_invariants/test_golden_dataset.py -v -k nifty
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analytics.replay.golden_dataset import GOLDEN_DIR, compare_results, load_expected


class TestGoldenDatasetRegression:
    """Verify replay engine produces consistent results."""

    @pytest.mark.golden
    def test_golden_dataset_directory_exists(self):
        """Golden root is configured (TOS-P4-001); replay datasets optional."""
        assert GOLDEN_DIR.exists(), (
            f"GOLDEN_DIR does not exist: {GOLDEN_DIR}. "
            "Expected tests/fixtures/golden or TRADEX_GOLDEN_DIR."
        )
        # Bus/cert fixtures count; replay date_symbol/ dirs are optional.
        has_fixtures = any(GOLDEN_DIR.glob("*.json")) or any(GOLDEN_DIR.glob("*_*/"))
        assert has_fixtures, (
            f"No golden fixtures in {GOLDEN_DIR}. "
            "Add bus/cert JSON fixtures or save a replay dataset via "
            "python -m analytics.replay.golden_dataset save --symbol NIFTY --date YYYY-MM-DD"
        )

    @pytest.mark.golden
    @pytest.mark.skipif(
        not (GOLDEN_DIR / "2026-05-12_NIFTY").exists(),
        reason="NIFTY 2026-05-12 golden dataset not available",
    )
    def test_golden_2026_05_12_nifty_structure(self):
        """Golden dataset should have expected.json with required fields."""
        expected = load_expected(GOLDEN_DIR / "2026-05-12_NIFTY")

        required_fields = [
            "bars_processed",
            "signals_generated",
            "total_trades",
            "win_rate",
            "final_equity",
            "total_return_pct",
            "max_drawdown_pct",
            "sharpe_ratio",
        ]

        for field in required_fields:
            assert field in expected, f"Missing required field: {field}"

    @pytest.mark.golden
    def test_golden_dataset_comparison_logic(self):
        """Test the comparison logic with mock data."""
        from analytics.replay.models import ReplayResult, ReplaySession

        # Create mock result
        session = ReplaySession(
            capital=100010.0,  # Capital includes trade PnL
            trades=[],
            equity_curve=[(None, 100000.0), (None, 100010.0)],
        )

        result = ReplayResult(
            session=session,
            bars_processed=100,
            signals_generated=10,
        )

        # Create matching expected
        expected = {
            "bars_processed": 100,
            "signals_generated": 10,
            "total_trades": 0,
            "win_rate": 0.0,
            "final_equity": 100010.0,
            "total_return_pct": 0.01,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
        }

        # Should have no mismatches
        mismatches = compare_results(result, expected)
        assert len(mismatches) == 0, f"Unexpected mismatches: {mismatches}"

    @pytest.mark.golden
    def test_golden_dataset_detects_drift(self):
        """Test that comparison logic detects behavioral drift."""
        from analytics.replay.models import ReplayResult, ReplaySession

        # Create result with different values
        session = ReplaySession(
            capital=100000.0,
            trades=[],
            equity_curve=[(None, 100000.0), (None, 102000.0)],
        )

        result = ReplayResult(
            session=session,
            bars_processed=150,  # Different from expected
            signals_generated=15,  # Different from expected
        )

        expected = {
            "bars_processed": 100,  # Expected different value
            "signals_generated": 10,  # Expected different value
            "total_trades": 0,
            "win_rate": 0.0,
            "final_equity": 100000.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
        }

        # Should detect mismatches
        mismatches = compare_results(result, expected)
        assert len(mismatches) > 0, "Should detect behavioral drift"
        assert any("bars_processed" in m for m in mismatches)
        assert any("signals_generated" in m for m in mismatches)
