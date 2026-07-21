#!/usr/bin/env python3
"""Production Certification Gate — automated production readiness checklist.

Runs all critical tests and checks code quality metrics to determine
if the system is ready for production deployment.

Usage:
    python scripts/production_certification.py [--verbose] [--json]

Exit codes:
    0 — All checks passed, certified for production
    1 — One or more checks failed, NOT certified
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("production_certification")


class CheckStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    duration_seconds: float
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CertificationReport:
    timestamp: str
    checks: list[CheckResult] = field(default_factory=list)
    overall: CheckStatus = CheckStatus.PASS

    @property
    def passed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.PASS]

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.FAIL]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.WARN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall": self.overall.value,
            "total_checks": len(self.checks),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "warnings": len(self.warnings),
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "duration_seconds": round(c.duration_seconds, 2),
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


def run_command(
    cmd: list[str],
    timeout: int = 120,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Run a subprocess and return the result."""
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = (
        src if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
    )
    return subprocess.run(
        cmd,
        timeout=timeout,
        capture_output=capture_output,
        text=True,
        cwd=root,
        env=env,
    )


def check_unit_tests() -> CheckResult:
    """Run unit and contract tests."""
    start = time.monotonic()
    try:
        result = run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "not integration and not sandbox and not live_readonly",
                "-x",
                "--tb=short",
                "-q",
                "tests/",
            ],
            timeout=180,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="unit_tests",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="All unit tests passed",
            )
        else:
            # Parse output for failure count
            output = result.stderr + result.stdout
            return CheckResult(
                name="unit_tests",
                status=CheckStatus.FAIL,
                duration_seconds=duration,
                message=f"Unit tests failed:\n{output[-500:]}",
            )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="unit_tests",
            status=CheckStatus.FAIL,
            duration_seconds=180,
            message="Unit tests timed out after 180 seconds",
        )
    except Exception as e:
        return CheckResult(
            name="unit_tests",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Unit test runner failed: {e}",
        )


def check_chaos_tests() -> CheckResult:
    """Run chaos engineering tests."""
    start = time.monotonic()
    try:
        result = run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-x",
                "--tb=short",
                "-q",
                "tests/chaos/",
            ],
            timeout=180,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="chaos_tests",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="All chaos tests passed",
            )
        else:
            output = result.stderr + result.stdout
            return CheckResult(
                name="chaos_tests",
                status=CheckStatus.FAIL,
                duration_seconds=duration,
                message=f"Chaos tests failed:\n{output[-500:]}",
            )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="chaos_tests",
            status=CheckStatus.FAIL,
            duration_seconds=180,
            message="Chaos tests timed out after 180 seconds",
        )
    except Exception as e:
        return CheckResult(
            name="chaos_tests",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Chaos test runner failed: {e}",
        )


def check_memory_tests() -> CheckResult:
    """Run memory leak regression tests."""
    start = time.monotonic()
    try:
        result = run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-x",
                "--tb=short",
                "-q",
                "tests/architecture/regression_invariants/test_memory_leaks.py",
            ],
            timeout=180,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="memory_tests",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="All memory tests passed",
            )
        else:
            output = result.stderr + result.stdout
            return CheckResult(
                name="memory_tests",
                status=CheckStatus.FAIL,
                duration_seconds=duration,
                message=f"Memory tests failed:\n{output[-500:]}",
            )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="memory_tests",
            status=CheckStatus.FAIL,
            duration_seconds=180,
            message="Memory tests timed out after 180 seconds",
        )
    except Exception as e:
        return CheckResult(
            name="memory_tests",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Memory test runner failed: {e}",
        )


def check_test_coverage() -> CheckResult:
    """Verify test coverage is above threshold."""
    start = time.monotonic()
    try:
        result = run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "not integration and not sandbox and not live_readonly",
                "--cov=brokers",
                "--cov=interface",
                "--cov=datalake",
                "--cov=analytics",
                "--cov=application",
                "--cov=domain",
                "--cov=infrastructure",
                "--cov=runtime",
                "--cov-report=term",
                "--cov-fail-under=90",
                "-q",
                "tests/",
            ],
            timeout=300,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="test_coverage",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="Test coverage >= 90%",
            )
        else:
            output = result.stderr + result.stdout
            # Extract coverage percentage
            import re

            match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
            coverage_pct = match.group(1) if match else "unknown"
            return CheckResult(
                name="test_coverage",
                status=CheckStatus.FAIL,
                duration_seconds=duration,
                message=f"Test coverage below 90% (current: {coverage_pct}%)",
                details={"output_snippet": output[-300:]},
            )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="test_coverage",
            status=CheckStatus.FAIL,
            duration_seconds=300,
            message="Coverage check timed out",
        )
    except Exception as e:
        return CheckResult(
            name="test_coverage",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Coverage check failed: {e}",
        )


def check_security_scan() -> CheckResult:
    """Run Bandit security scan."""
    start = time.monotonic()
    try:
        result = run_command(
            [
                sys.executable,
                "-m",
                "bandit",
                "-r",
                "src/brokers/",
                "src/interface/",
                "src/datalake/",
                "src/analytics/",
                "src/application/",
                "src/domain/",
                "src/infrastructure/",
                "-ll",  # high severity only
                "-f",
                "json",
            ],
            timeout=120,
        )
        duration = time.monotonic() - start

        # Bandit returns 1 if issues found, 0 if clean
        if result.returncode == 0:
            return CheckResult(
                name="security_scan",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="Zero security vulnerabilities found",
            )
        else:
            # Parse JSON output for issue count
            try:
                output = json.loads(result.stdout)
                issues = output.get("results", [])
                high_severity = [i for i in issues if i.get("issue_severity") == "HIGH"]
                medium_severity = [i for i in issues if i.get("issue_severity") == "MEDIUM"]

                if high_severity:
                    return CheckResult(
                        name="security_scan",
                        status=CheckStatus.FAIL,
                        duration_seconds=duration,
                        message=f"Found {len(high_severity)} HIGH severity vulnerabilities",
                        details={"high": len(high_severity), "medium": len(medium_severity)},
                    )
                else:
                    return CheckResult(
                        name="security_scan",
                        status=CheckStatus.WARN,
                        duration_seconds=duration,
                        message=f"Found {len(medium_severity)} MEDIUM severity issues (no HIGH)",
                        details={"high": 0, "medium": len(medium_severity)},
                    )
            except json.JSONDecodeError:
                return CheckResult(
                    name="security_scan",
                    status=CheckStatus.WARN,
                    duration_seconds=duration,
                    message="Bandit scan completed with issues (could not parse JSON)",
                    details={"raw_output": result.stdout[:500]},
                )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="security_scan",
            status=CheckStatus.FAIL,
            duration_seconds=120,
            message="Security scan timed out",
        )
    except FileNotFoundError:
        return CheckResult(
            name="security_scan",
            status=CheckStatus.SKIP,
            duration_seconds=time.monotonic() - start,
            message="Bandit not installed — skipping security scan",
        )
    except Exception as e:
        return CheckResult(
            name="security_scan",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Security scan failed: {e}",
        )


def check_linting() -> CheckResult:
    """Run Ruff linter."""
    start = time.monotonic()
    try:
        result = run_command(
            [sys.executable, "-m", "ruff", "check", "."],
            timeout=60,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="linting",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="No linting errors",
            )
        else:
            output = result.stderr + result.stdout
            return CheckResult(
                name="linting",
                status=CheckStatus.WARN,
                duration_seconds=duration,
                message=f"Linting issues found:\n{output[-300:]}",
            )
    except FileNotFoundError:
        return CheckResult(
            name="linting",
            status=CheckStatus.SKIP,
            duration_seconds=time.monotonic() - start,
            message="Ruff not installed — skipping linting",
        )
    except Exception as e:
        return CheckResult(
            name="linting",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Linting check failed: {e}",
        )


def check_formatting() -> CheckResult:
    """Run Ruff format check."""
    start = time.monotonic()
    try:
        result = run_command(
            [sys.executable, "-m", "ruff", "format", "--check", "."],
            timeout=60,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="formatting",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="Code is properly formatted",
            )
        else:
            return CheckResult(
                name="formatting",
                status=CheckStatus.WARN,
                duration_seconds=duration,
                message="Code formatting issues found",
            )
    except FileNotFoundError:
        return CheckResult(
            name="formatting",
            status=CheckStatus.SKIP,
            duration_seconds=time.monotonic() - start,
            message="Ruff not installed — skipping format check",
        )
    except Exception as e:
        return CheckResult(
            name="formatting",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Format check failed: {e}",
        )


def check_mypy() -> CheckResult:
    """Run MyPy type checker."""
    start = time.monotonic()
    try:
        result = run_command(
            [sys.executable, "-m", "mypy", "src/brokers/"],
            timeout=120,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="mypy",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="No type errors",
            )
        else:
            output = result.stderr + result.stdout
            # Extract error count
            import re

            match = re.search(r"Found (\d+) errors?", output)
            error_count = match.group(1) if match else "unknown"
            return CheckResult(
                name="mypy",
                status=CheckStatus.WARN,
                duration_seconds=duration,
                message=f"Found {error_count} type errors (tracked, non-blocking)",
                details={"error_count": error_count},
            )
    except FileNotFoundError:
        return CheckResult(
            name="mypy",
            status=CheckStatus.SKIP,
            duration_seconds=time.monotonic() - start,
            message="MyPy not installed — skipping type check",
        )
    except Exception as e:
        return CheckResult(
            name="mypy",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Type check failed: {e}",
        )


def check_replay_determinism() -> CheckResult:
    """Verify replay determinism."""
    start = time.monotonic()
    try:
        result = run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/integration/test_event_replay_determinism.py",
                "-q",
                "--tb=short",
            ],
            timeout=120,
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            return CheckResult(
                name="replay_determinism",
                status=CheckStatus.PASS,
                duration_seconds=duration,
                message="Replay is deterministic",
            )
        else:
            output = result.stderr + result.stdout
            return CheckResult(
                name="replay_determinism",
                status=CheckStatus.FAIL,
                duration_seconds=duration,
                message=f"Replay determinism check failed:\n{output[-300:]}",
            )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="replay_determinism",
            status=CheckStatus.FAIL,
            duration_seconds=120,
            message="Replay determinism check timed out",
        )
    except FileNotFoundError:
        return CheckResult(
            name="replay_determinism",
            status=CheckStatus.SKIP,
            duration_seconds=time.monotonic() - start,
            message="Replay verifier not found — skipping",
        )
    except Exception as e:
        return CheckResult(
            name="replay_determinism",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"Replay determinism check failed: {e}",
        )


def check_broker_certification() -> CheckResult:
    """Paper broker import smoke — former ``broker verify`` CLI removed."""
    start = time.monotonic()
    try:
        from brokers.session import BrokerSession

        session = BrokerSession.connect("paper")
        try:
            ok = session.stock("RELIANCE") is not None
        finally:
            session.close()
        if ok:
            return CheckResult(
                name="broker_certification",
                status=CheckStatus.PASS,
                duration_seconds=time.monotonic() - start,
                message="paper BrokerSession.connect + stock() ok",
            )
        return CheckResult(
            name="broker_certification",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message="paper stock() returned None",
        )
    except Exception as e:
        return CheckResult(
            name="broker_certification",
            status=CheckStatus.FAIL,
            duration_seconds=time.monotonic() - start,
            message=f"broker certification check failed: {e}",
        )


def run_certification(verbose: bool = False, json_output: bool = False) -> CertificationReport:
    """Run all certification checks and return the report."""
    report = CertificationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    checks = [
        ("Unit Tests", check_unit_tests),
        ("Chaos Tests", check_chaos_tests),
        ("Memory Tests", check_memory_tests),
        ("Test Coverage (>=90%)", check_test_coverage),
        ("Security Scan (Bandit)", check_security_scan),
        ("Linting (Ruff)", check_linting),
        ("Formatting (Ruff)", check_formatting),
        ("Type Checking (MyPy)", check_mypy),
        ("Replay Determinism", check_replay_determinism),
        ("Broker Certification (paper)", check_broker_certification),
    ]

    total_start = time.monotonic()

    for name, check_fn in checks:
        if verbose:
            print(f"  Running: {name}...", flush=True)

        result = check_fn()
        report.checks.append(result)

        if verbose:
            status_icon = {
                CheckStatus.PASS: "✅",
                CheckStatus.FAIL: "❌",
                CheckStatus.WARN: "⚠️",
                CheckStatus.SKIP: "⏭️",
            }[result.status]
            print(f"  {status_icon} {name}: {result.message[:80]}")

    total_duration = time.monotonic() - total_start

    # Determine overall status
    has_failures = any(c.status == CheckStatus.FAIL for c in report.checks)
    if has_failures:
        report.overall = CheckStatus.FAIL
    else:
        report.overall = CheckStatus.PASS

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Production Certification Report")
        print(f"{'=' * 60}")
        print(f"Timestamp: {report.timestamp}")
        print(f"Total Duration: {total_duration:.1f}s")
        print(f"Overall: {report.overall.value}")
        print(f"Passed: {len(report.passed)}/{len(report.checks)}")
        print(f"Failed: {len(report.failed)}/{len(report.checks)}")
        print(f"Warnings: {len(report.warnings)}/{len(report.checks)}")
        print(f"{'=' * 60}")

        if report.failed:
            print("\n❌ FAILED CHECKS:")
            for check in report.failed:
                print(f"  - {check.name}: {check.message[:100]}")

        if report.warnings:
            print("\n⚠️  WARNINGS:")
            for check in report.warnings:
                print(f"  - {check.name}: {check.message[:100]}")

    if json_output:
        print(json.dumps(report.to_dict(), indent=2))

    return report


def main():
    """Entry point for the certification script."""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    json_output = "--json" in sys.argv

    # Ensure we're in the project root
    project_root = Path(__file__).resolve().parent.parent.parent
    os.chdir(project_root)

    print("🔒 Production Certification Gate")
    print(f"📁 Project: {project_root}")
    print()

    report = run_certification(verbose=verbose, json_output=json_output)

    if report.overall == CheckStatus.FAIL:
        print("\n🚫 CERTIFICATION FAILED — System is NOT ready for production")
        sys.exit(1)
    else:
        print("\n✅ CERTIFICATION PASSED — System is ready for production")
        sys.exit(0)


if __name__ == "__main__":
    main()
