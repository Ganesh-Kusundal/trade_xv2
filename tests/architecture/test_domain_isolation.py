"""Architecture tests: enforce domain layer isolation.

Verifies that the domain layer never imports from application, brokers, analytics, api, or cli.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]





def _extract_import_root(stmt: ast.stmt) -> str | None:
    """Extract the top-level module name from an import statement."""
    if isinstance(stmt, ast.Import):
        if stmt.names:
            return stmt.names[0].name.split(".")[0]
    elif isinstance(stmt, ast.ImportFrom):  # noqa: SIM102
        if stmt.module:
            return stmt.module.split(".")[0]
    return None


class TestDomainIsolation:
    """Domain layer must not import from application/brokers/analytics/api/cli."""

    @pytest.mark.parametrize(
        "forbidden",
        ["application", "brokers", "analytics", "api", "cli", "config", "infrastructure", "datalake"],
    )
    def test_domain_does_not_import_from(self, forbidden: str) -> None:
        """Domain files must not import from forbidden layers."""
        domain_dir = ROOT / "domain"
        violations: list[str] = []

        for f in domain_dir.rglob("*.py"):
            if f.name == "__pycache__" or ".tests." in str(f):
                continue
            try:
                tree = ast.parse(f.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    root = _extract_import_root(node)
                    if root == forbidden:
                        violations.append(f"{f.relative_to(ROOT)}:{node.lineno}")

        assert not violations, (
            f"Domain imports from '{forbidden}' at: {violations}. "
            f"Domain layer must be independent of application/brokers/analytics."
        )
