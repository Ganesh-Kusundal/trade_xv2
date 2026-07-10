"""Architecture fitness: production packages must not import tradex.runtime.

``tradex.runtime`` is a deprecated backward-compat facade. Canonical imports
are ``domain.*``, ``application.*``, ``infrastructure.*``, and ``runtime.*``
(composition roots only).

This test scans production modules only (excludes ``tests/`` trees and the
facade package itself). Scripts are excluded (tooling, not library layers).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Library / service packages that must not depend on the facade.
PROD_PACKAGES = (
    "src/domain",
    "application",
    "infrastructure",
    "brokers",
    "cli",
    "api",
    "config",
    "datalake",
    "analytics",
    "runtime",
)

# Allow the facade package itself (and its deprecation helper).
FACADE_PREFIX = ("tradex", "runtime")


def _is_excluded(path: Path) -> bool:
    parts = path.parts
    if "__pycache__" in parts:
        return True
    if "tests" in parts:
        return True
    if path.name.startswith("test_") or path.name.endswith("_test.py"):
        return True
    # facade package
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return True
    if rel.parts[:2] == FACADE_PREFIX:
        return True
    return False


def _iter_prod_files() -> list[Path]:
    files: list[Path] = []
    for pkg in PROD_PACKAGES:
        base = ROOT / pkg
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if _is_excluded(path):
                continue
            files.append(path)
    assert files, "Production scanner found zero files — path layout may have drifted"
    return files


def _tradex_runtime_hits(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tradex.runtime" or alias.name.startswith(
                    "tradex.runtime."
                ):
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "tradex.runtime" or node.module.startswith(
                "tradex.runtime."
            ):
                hits.append((node.lineno, node.module))
    return hits


class TestNoTradexRuntimeInProduction:
    def test_scan_is_non_empty(self) -> None:
        assert len(_iter_prod_files()) >= 50

    def test_no_production_imports_tradex_runtime(self) -> None:
        violations: list[str] = []
        for path in _iter_prod_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                violations.append(f"{path.relative_to(ROOT)}: SyntaxError: {exc}")
                continue
            for lineno, module in _tradex_runtime_hits(tree):
                violations.append(
                    f"{path.relative_to(ROOT)}:{lineno}: import {module}"
                )

        assert not violations, (
            "Production packages must not import tradex.runtime "
            "(use domain/application/infrastructure/runtime instead):\n"
            + "\n".join(violations)
        )


@pytest.mark.parametrize(
    "path",
    _iter_prod_files()[:5],  # light parse sanity; full scan above
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_sample_prod_files_parse(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
