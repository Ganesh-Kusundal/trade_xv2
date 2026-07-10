#!/usr/bin/env python3
"""Flaky test detection script.

Runs tests multiple times and identifies tests that fail intermittently.
Usage:
    python scripts/detect_flaky_tests.py [test_path] [--runs N]

Example:
    python scripts/detect_flaky_tests.py tests/e2e/ --runs 5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_tests(test_path: str, run_number: int) -> dict:
    """Run tests once and return results."""
    cmd = [
        "pytest",
        test_path,
        "-v",
        "--tb=no",
        "-q",
        "--json-report",
        "--json-report-file=-",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutes timeout
    )

    # Parse JSON report from stdout
    try:
        # JSON report is written to file, read it
        report_file = Path("pytest-report.json")
        if report_file.exists():
            with open(report_file) as f:
                return json.load(f)
    except Exception:
        pass

    return {"tests": [], "summary": {}}


def detect_flaky_tests(test_path: str, num_runs: int = 3) -> list[dict]:
    """Run tests multiple times and detect flaky ones.

    A test is considered flaky if it passes sometimes and fails others.
    """
    print(f"Running flaky test detection: {num_runs} runs for {test_path}")
    print("=" * 80)

    test_results: dict[str, list[bool]] = {}

    for run_idx in range(num_runs):
        print(f"\nRun {run_idx + 1}/{num_runs}...")

        cmd = [
            "pytest",
            test_path,
            "-v",
            "--tb=line",
            "-q",
            "--durations=0",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Parse test results from output
        # Look for PASSED/FAILED lines
        for line in result.stdout.split("\n"):
            if "PASSED" in line or "FAILED" in line or "ERROR" in line:
                # Extract test name
                parts = line.split()
                if len(parts) >= 2:
                    test_name = parts[0]
                    if "::" in test_name:
                        passed = "PASSED" in line
                        if test_name not in test_results:
                            test_results[test_name] = []
                        test_results[test_name].append(passed)

    # Identify flaky tests
    flaky_tests = []
    for test_name, results in test_results.items():
        if len(results) < num_runs:
            # Test didn't run all times (error or skipped)
            continue

        passed_count = sum(results)
        failed_count = num_runs - passed_count

        if passed_count > 0 and failed_count > 0:
            # Test is flaky
            flaky_tests.append(
                {
                    "test": test_name,
                    "passed": passed_count,
                    "failed": failed_count,
                    "flakiness_rate": failed_count / num_runs,
                }
            )

    return flaky_tests


def main():
    parser = argparse.ArgumentParser(description="Detect flaky tests")
    parser.add_argument("test_path", help="Path to test file or directory")
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of times to run tests (default: 3)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="flaky-tests.json",
        help="Output file for flaky test report",
    )

    args = parser.parse_args()

    flaky_tests = detect_flaky_tests(args.test_path, args.runs)

    if flaky_tests:
        print("\n" + "=" * 80)
        print("FLAKY TESTS DETECTED")
        print("=" * 80)

        for test in sorted(flaky_tests, key=lambda x: x["flakiness_rate"], reverse=True):
            print(f"\n{test['test']}")
            print(f"  Passed: {test['passed']}/{args.runs}")
            print(f"  Failed: {test['failed']}/{args.runs}")
            print(f"  Flakiness: {test['flakiness_rate']:.0%}")

        # Save report
        with open(args.output, "w") as f:
            json.dump(flaky_tests, f, indent=2)

        print(f"\nReport saved to: {args.output}")
        print("\nRecommendation: Fix or quarantine these tests")
        sys.exit(1)
    else:
        print("\n" + "=" * 80)
        print("NO FLAKY TESTS DETECTED")
        print("=" * 80)
        print(f"All tests passed consistently across {args.runs} runs")
        sys.exit(0)


if __name__ == "__main__":
    main()
