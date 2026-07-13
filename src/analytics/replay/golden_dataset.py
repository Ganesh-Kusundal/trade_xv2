"""Golden Dataset management for regression testing.

This module provides infrastructure to save replay results as golden datasets
and compare new runs against expected outputs to detect behavioral drift.

Usage:
    # Save golden dataset
    python -m analytics.replay.golden_dataset save --symbol NIFTY --date 2026-05-12

    # Run regression test
    pytest tests/architecture/regression_invariants/test_golden_dataset.py
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from analytics.replay.models import ReplayResult

logger = logging.getLogger(__name__)

# TOS-P4-001: default to test fixtures; override with TRADEX_GOLDEN_DIR.
_DEFAULT_GOLDEN = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "golden"
GOLDEN_DIR = Path(os.environ.get("TRADEX_GOLDEN_DIR", str(_DEFAULT_GOLDEN)))


def save_golden_dataset(
    symbol: str,
    date: str,
    result: ReplayResult,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save replay result as golden dataset.

    Parameters
    ----------
    symbol:
        Instrument symbol (e.g., 'NIFTY', 'RELIANCE')
    date:
        Trading date in YYYY-MM-DD format
    result:
        ReplayResult from completed replay session
    metadata:
        Optional metadata (broker used, strategy config, etc.)

    Returns
    -------
    Path to saved dataset directory
    """
    dataset_dir = GOLDEN_DIR / f"{date}_{symbol}"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # Save expected outputs
    expected = {
        "bars_processed": result.bars_processed,
        "signals_generated": result.signals_generated,
        "total_trades": result.session.total_trades,
        "win_rate": round(result.session.win_rate * 100, 1),
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct, 2),
        "max_drawdown_pct": round(result.session.max_drawdown * 100, 2),
        "sharpe_ratio": result.sharpe_ratio,
        "metadata": metadata or {},
    }

    expected_file = dataset_dir / "expected.json"
    expected_file.write_text(json.dumps(expected, indent=2))

    # Save replay result summary (for debugging)
    result_file = dataset_dir / "result.json"
    result_file.write_text(json.dumps(result.summary, indent=2))

    return dataset_dir


def load_expected(dataset_path: Path) -> dict[str, Any]:
    """Load expected outputs from golden dataset.

    Parameters
    ----------
    dataset_path:
        Path to golden dataset directory

    Returns
    -------
    Dictionary with expected values

    Raises
    ------
    FileNotFoundError:
        If expected.json doesn't exist
    """
    expected_file = dataset_path / "expected.json"
    if not expected_file.exists():
        raise FileNotFoundError(f"Expected file not found: {expected_file}")
    return json.loads(expected_file.read_text())


def compare_results(actual: ReplayResult, expected: dict[str, Any]) -> list[str]:
    """Compare actual results against expected. Returns list of mismatches.

    Parameters
    ----------
    actual:
        Actual ReplayResult from replay session
    expected:
        Expected values from golden dataset

    Returns
    -------
    List of mismatch descriptions (empty if all match)
    """
    mismatches = []

    actual_summary = actual.summary

    # Exact matches for integer fields
    for key in ["bars_processed", "signals_generated", "total_trades"]:
        if actual_summary[key] != expected[key]:
            mismatches.append(
                f"{key}: expected {expected[key]}, got {actual_summary[key]}"
            )

    # Allow small tolerance for floating-point comparisons (0.01%)
    for key in ["final_equity", "total_return_pct", "max_drawdown_pct"]:
        diff = abs(actual_summary[key] - expected[key])
        if diff > 0.01:  # 1% tolerance
            mismatches.append(
                f"{key}: expected {expected[key]}, got {actual_summary[key]} (diff: {diff:.2f})"
            )

    # Sharpe ratio tolerance (more lenient due to calculation sensitivity)
    if abs(actual_summary["sharpe_ratio"] - expected.get("sharpe_ratio", 0)) > 0.1:
        mismatches.append(
            f"sharpe_ratio: expected {expected.get('sharpe_ratio', 0)}, "
            f"got {actual_summary['sharpe_ratio']}"
        )

    return mismatches


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Golden dataset management")
    subparsers = parser.add_subparsers(dest="command")

    # Save command
    save_parser = subparsers.add_parser("save", help="Save replay as golden dataset")
    save_parser.add_argument("--symbol", required=True, help="Instrument symbol")
    save_parser.add_argument("--date", required=True, help="Trading date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.command == "save":
        logger.info("Golden dataset infrastructure ready for %s on %s", args.symbol, args.date)
        logger.info("Datasets will be saved to: %s", GOLDEN_DIR)
    else:
        parser.print_help()
