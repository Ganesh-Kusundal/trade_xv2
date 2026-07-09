"""Architecture tests: enforce single-source-of-truth for error hierarchies.

Canonical home (post brokers.common → tradex.runtime migration):
``tradex.runtime.resilience.errors``. Thin shims under ``brokers.common`` may
re-export but must not redefine ``BrokerError``.
"""
from __future__ import annotations

import ast
from pathlib import Path

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
        """Only tradex.runtime.resilience.errors should define class BrokerError."""
        canonical_file = ROOT / "tradex/runtime/resilience/errors.py"
        assert canonical_file.exists(), f"Canonical file missing: {canonical_file}"

        dirs_to_check = [
            "domain",
            "application",
            "analytics",
            "api",
            "cli",
            "config",
            "infrastructure",
            "datalake",
            "brokers",
        ]
        files = _find_python_files(dirs_to_check)

        # Allow re-export modules (no ClassDef of BrokerError expected there)
        allow_prefixes = (
            "tradex/runtime/resilience/errors.py",
        )
        violations: list[str] = []
        for f in files:
            rel = str(f.relative_to(ROOT))
            if rel in allow_prefixes:
                continue
            try:
                tree = ast.parse(f.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "BrokerError":
                    violations.append(f"{rel}:{node.lineno}")

        assert not violations, (
            f"Duplicate BrokerError definitions found in: {violations}. "
            f"Only tradex.runtime.resilience.errors should define it."
        )

    def test_resilience_errors_is_canonical_root(self) -> None:
        from tradex.runtime.resilience.errors import BrokerError, TradeXV2Error

        assert issubclass(BrokerError, TradeXV2Error)

    def test_runtime_errors_is_single_import_path(self) -> None:
        """BrokerError must only be imported from tradex.runtime.resilience.errors."""
        from tradex.runtime.resilience.errors import BrokerError as CanonicalBrokerError
        from tradex.runtime.resilience import errors as resilience_errors

        assert CanonicalBrokerError is resilience_errors.BrokerError
