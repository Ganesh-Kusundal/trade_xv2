"""datalake/ must not import application/ — federation is injected via fetch_fn."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATALAKE_ROOT = REPO_ROOT / "src" / "datalake"


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _application_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(REPO_ROOT)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "application" or alias.name.startswith("application."):
                    hits.append(f"{rel}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "application" or node.module.startswith("application."):
                hits.append(f"{rel}: from {node.module} import ...")
    return hits


@pytest.mark.architecture
def test_datalake_does_not_import_application() -> None:
    violations: list[str] = []
    for py_file in _python_files(DATALAKE_ROOT):
        violations.extend(_application_imports(py_file))
    assert not violations, "datalake -> application imports:\n" + "\n".join(violations)
