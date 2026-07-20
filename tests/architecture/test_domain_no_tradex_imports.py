"""Architecture fitness: domain must never import tradex (or outer layers via tradex).

The domain package is the innermost layer. Dual PYTHONPATH is ``src:.`` so the
package name is ``domain``. Importing ``tradex`` (composition root / runtime)
from production domain modules breaks dependency inversion.

AST-based import detection is used so comments and docstrings that mention
``tradex.connect`` / ``tradex.runtime.*`` do not trigger false positives.

Production modules under ``src/domain/`` are scanned; ``tests`` subtrees and
``__pycache__`` are excluded (domain tests may exercise the composition root).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOMAIN_DIR = ROOT / "src" / "domain"
FORBIDDEN_ROOT = "tradex"


def _iter_domain_prod_files() -> list[Path]:
    files = [
        f
        for f in DOMAIN_DIR.rglob("*.py")
        if "__pycache__" not in f.parts and "tests" not in f.parts
    ]
    assert files, (
        f"Domain tradex-isolation scanner found zero Python files under {DOMAIN_DIR}. "
        f"Expected src-layout package at src/domain."
    )
    return files


def _tradex_import_hits(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, imported_module) for any real tradex import."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == FORBIDDEN_ROOT:
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root == FORBIDDEN_ROOT:
                hits.append((node.lineno, node.module))
    return hits


class TestDomainDoesNotImportTradex:
    """Production domain must not depend on the tradex composition root."""

    def test_domain_scan_is_non_empty(self) -> None:
        files = _iter_domain_prod_files()
        assert len(files) >= 20

    def test_no_production_domain_imports_tradex(self) -> None:
        violations: list[str] = []
        for path in _iter_domain_prod_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                violations.append(f"{path.relative_to(ROOT)}: SyntaxError: {exc}")
                continue
            for lineno, module in _tradex_import_hits(tree):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: import {module}")

        assert not violations, (
            "Production domain must not import tradex "
            "(domain is the innermost layer; wire via ports / composition root):\n"
            + "\n".join(violations)
        )


@pytest.mark.parametrize("path", _iter_domain_prod_files())
def test_each_domain_prod_file_parses(path: Path) -> None:
    """Sanity: every production domain module still parses for the scanner."""
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
