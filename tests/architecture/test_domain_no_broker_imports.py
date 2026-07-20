"""Domain layer must not import broker packages (TRANS-P3-010)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_ROOT = REPO_ROOT / "src" / "domain"

_FORBIDDEN_PREFIXES = ("brokers.", "brokers/")


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _import_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(REPO_ROOT)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "brokers" or alias.name.startswith("brokers."):
                    hits.append(f"{rel}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "brokers" or node.module.startswith("brokers."):
                hits.append(f"{rel}: from {node.module} import ...")
    return hits


@pytest.mark.architecture
def test_domain_has_no_broker_imports() -> None:
    violations: list[str] = []
    for py_file in _python_files(DOMAIN_ROOT):
        violations.extend(_import_violations(py_file))
    assert not violations, "Domain broker leakage:\n" + "\n".join(violations)
