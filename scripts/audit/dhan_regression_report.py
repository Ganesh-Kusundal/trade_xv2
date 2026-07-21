#!/usr/bin/env python3
"""Parse pytest JUnit XML output and emit a capability-level regression report.

Usage
-----
    python scripts/dhan_regression_report.py \\
        --junit reports/off_market_regression.xml \\
        --output docs/audits/DHAN_REGRESSION_REPORT.md \\
        --fail-on P0

Exit codes
----------
    0  — all required capabilities passed (or --fail-on threshold not hit)
    1  — at least one capability at the specified severity failed
    2  — JUnit XML file not found / parse error
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Map test ids (case.id) to their capability + severity — reuse manifest data
try:
    from tests.integration.brokers.providers.dhan.regression.manifest import (
        MARKET_HOURS_CASES,
        OFF_MARKET_CASES,
    )

    _MANIFEST_LOADED = True
    _CASE_MAP = {c.id: c for c in OFF_MARKET_CASES + MARKET_HOURS_CASES}
except ImportError:
    _MANIFEST_LOADED = False
    _CASE_MAP = {}


@dataclass
class TestResult:
    name: str
    classname: str
    status: str  # "passed" | "failed" | "skipped" | "error"
    duration_s: float
    message: str = ""
    # resolved from manifest
    capability: str = "unknown"
    severity: str = "P1"
    tier: str = "unknown"


def parse_junit(path: Path) -> list[TestResult]:
    """Parse a JUnit XML file and return a list of TestResult objects."""
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"ERROR: Cannot parse {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    except FileNotFoundError:
        print(f"ERROR: JUnit XML not found: {path}", file=sys.stderr)
        sys.exit(2)

    results: list[TestResult] = []
    for tc in tree.iter("testcase"):
        name = tc.attrib.get("name", "")
        classname = tc.attrib.get("classname", "")
        duration = float(tc.attrib.get("time", "0"))

        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            status = "failed"
            message = (failure.attrib.get("message") or failure.text or "")[:300]
        elif error is not None:
            status = "error"
            message = (error.attrib.get("message") or error.text or "")[:300]
        elif skipped is not None:
            status = "skipped"
            message = skipped.attrib.get("message", "")[:200]
        else:
            status = "passed"
            message = ""

        # Try to resolve from manifest — test id is the last part of name
        # parametrize format: "test_off_market_regression[nse_ltp]"
        case_id = ""
        if "[" in name and name.endswith("]"):
            case_id = name.split("[")[-1].rstrip("]")

        case = _CASE_MAP.get(case_id)
        results.append(
            TestResult(
                name=name,
                classname=classname,
                status=status,
                duration_s=duration,
                message=message,
                capability=case.capability if case else "unknown",
                severity=case.severity if case else "P1",
                tier=case.tier if case else "unknown",
            )
        )
    return results


def _severity_rank(s: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2}.get(s, 9)


def build_report(results: list[TestResult]) -> str:
    """Build a markdown capability-level report from parsed test results."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status in ("failed", "error"))
    skipped = sum(1 for r in results if r.status == "skipped")

    lines: list[str] = [
        "# Dhan Regression Report",
        f"\nGenerated: {timestamp}  ",
        f"Total: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}\n",
    ]

    # Summary badges
    if failed == 0:
        lines.append("> All tested capabilities passed.\n")
    else:
        lines.append(f"> :warning: **{failed} test(s) failed** — see details below.\n")

    # Per-tier breakdown
    tiers = ["off_market_safe", "market_hours", "pre_prod", "sandbox", "unknown"]
    for tier in tiers:
        tier_results = [r for r in results if r.tier == tier]
        if not tier_results:
            continue
        t_pass = sum(1 for r in tier_results if r.status == "passed")
        t_fail = sum(1 for r in tier_results if r.status in ("failed", "error"))
        t_skip = sum(1 for r in tier_results if r.status == "skipped")
        lines.append(f"## Tier: `{tier}`")
        lines.append(f"Passed: {t_pass} | Failed: {t_fail} | Skipped: {t_skip}\n")
        lines.append("| Test | Capability | Severity | Status | Duration |")
        lines.append("|------|-----------|----------|--------|----------|")
        for r in sorted(tier_results, key=lambda x: (_severity_rank(x.severity), x.name)):
            icon = {"passed": "✅", "failed": "❌", "error": "💥", "skipped": "⏭"}.get(
                r.status, "?"
            )
            lines.append(
                f"| `{r.name}` | `{r.capability}` | {r.severity} "
                f"| {icon} {r.status} | {r.duration_s:.2f}s |"
            )
        lines.append("")

    # Failed / error details
    failures = [r for r in results if r.status in ("failed", "error")]
    if failures:
        lines.append("## Failure Details\n")
        for r in sorted(failures, key=lambda x: _severity_rank(x.severity)):
            lines.append(f"### ❌ `{r.name}` ({r.severity})")
            lines.append(f"Capability: `{r.capability}` | Tier: `{r.tier}`")
            if r.message:
                lines.append(f"\n```\n{r.message}\n```")
            lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse pytest JUnit XML and emit a Dhan capability regression report."
    )
    parser.add_argument(
        "--junit",
        required=True,
        type=Path,
        help="Path to pytest JUnit XML output file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write the markdown report (defaults to stdout).",
    )
    parser.add_argument(
        "--fail-on",
        choices=["P0", "P1", "P2"],
        default="P0",
        help="Exit non-zero if any case at this severity or higher failed.",
    )
    args = parser.parse_args()

    results = parse_junit(args.junit)
    report = build_report(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)

    # Determine exit code
    threshold = _severity_rank(args.fail_on)
    failures = [r for r in results if r.status in ("failed", "error")]
    blocking = [r for r in failures if _severity_rank(r.severity) <= threshold]

    if blocking:
        print(
            f"\nBLOCKING: {len(blocking)} {args.fail_on}+ failure(s) detected:",
            file=sys.stderr,
        )
        for r in blocking:
            print(f"  [{r.severity}] {r.name}: {r.message[:120]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
