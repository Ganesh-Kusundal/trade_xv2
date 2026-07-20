"""Fitness: production datalake must not import analytics.

Direction allowed: analytics → datalake (via adapters/ports).
Direction forbidden: datalake → analytics (creates a cycle / layering violation).

Tests under tests/unit/datalake/ may still exercise analytics (allowed).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATALAKE = ROOT / "src" / "datalake"


def _iter_prod_py_files() -> list[Path]:
    files: list[Path] = []
    for path in DATALAKE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if "tests" in path.parts:
            continue
        files.append(path)
    return files


def _import_targets(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, module) for imports of analytics or analytics.*."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "analytics":
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root == "analytics":
                hits.append((node.lineno, node.module))
    return hits


class TestDatalakeDoesNotImportAnalytics:
    def test_no_production_datalake_imports_analytics(self) -> None:
        violations: list[str] = []
        for path in _iter_prod_py_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                violations.append(f"{path.relative_to(ROOT)}: SyntaxError: {exc}")
                continue
            for lineno, module in _import_targets(tree):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: import {module}")

        assert not violations, (
            "Production datalake must not import analytics "
            "(breaks layering / creates cycles):\n" + "\n".join(violations)
        )


@pytest.mark.parametrize("path", _iter_prod_py_files())
def test_each_prod_file_parses(path: Path) -> None:
    """Sanity: every production datalake module still parses."""
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
