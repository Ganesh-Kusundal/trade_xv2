"""Architecture tests: enforce single-source-of-truth for error hierarchies.

Verifies that:
1. brokers.common.resilience.errors is the canonical BrokerError root
2. brokers.common.errors re-exports from resilience.errors (no duplicate definitions)
3. No other module defines its own BrokerError class
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _find_python_files(directories: list[str]) -> list[Path]:
    files = []
    for d in directories:
        dir_path = ROOT / d
        if dir_path.exists():
            files.extend(dir_path.rglob("*.py"))
    return files


class TestNoDuplicateBrokerError:
    """Ensure only one BrokerError class definition exists in the codebase."""

    def test_only_one_broker_error_definition(self) -> None:
        """Only brokers.common.resilience.errors should define class BrokerError."""
        canonical_file = ROOT / "brokers/common/resilience/errors.py"
        assert canonical_file.exists(), f"Canonical file missing: {canonical_file}"

        dirs_to_check = ["domain", "application", "analytics", "api", "cli", "config", "infrastructure", "datalake"]
        files = _find_python_files(dirs_to_check)

        violations: list[str] = []
        for f in files:
            if f == canonical_file:
                continue
            try:
                tree = ast.parse(f.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "BrokerError":
                    violations.append(f"{f.relative_to(ROOT)}:{node.lineno}")

        # brokers/common/errors.py is allowed (it re-exports)
        allowed = {str((ROOT / "brokers/common/errors.py").relative_to(ROOT))}
        violations = [v for v in violations if not any(v.startswith(a) for a in allowed)]

        assert not violations, (
            f"Duplicate BrokerError definitions found in: {violations}. "
            f"Only brokers.common.resilience.errors should define it."
        )

    def test_resilience_errors_is_canonical_root(self) -> None:
        """brokers.common.resilience.errors.BrokerError should inherit from TradeXV2Error."""
        from brokers.common.resilience.errors import BrokerError, TradeXV2Error

        assert issubclass(BrokerError, TradeXV2Error), (
            "BrokerError should inherit from TradeXV2Error (canonical root)"
        )

    def test_common_errors_reexports_canonical(self) -> None:
        """brokers.common.errors.BrokerError should be the same object as resilience.errors.BrokerError."""
        from brokers.common.errors import BrokerError as CommonBrokerError
        from brokers.common.resilience.errors import BrokerError as ResilienceBrokerError

        assert CommonBrokerError is ResilienceBrokerError, (
            "brokers.common.errors.BrokerError should be a re-export of "
            "brokers.common.resilience.errors.BrokerError"
        )
