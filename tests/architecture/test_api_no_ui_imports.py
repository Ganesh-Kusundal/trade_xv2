"""Phase 3 layering — API must not import interface.ui (F9)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2] / "src" / "interface" / "api"


def _ui_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod == "interface.ui" or mod.startswith("interface.ui."):
                hits.append(f"{path.name}: from {mod}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "interface.ui" or alias.name.startswith("interface.ui."):
                    hits.append(f"{path.name}: import {alias.name}")
    return hits


@pytest.mark.architecture
def test_api_does_not_import_interface_ui() -> None:
    """F9: no ``from interface.ui`` under ``src/interface/api/``."""
    violations: list[str] = []
    for path in API_ROOT.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        violations.extend(_ui_imports(path))
    assert not violations, (
        "interface.api must not import interface.ui (Phase 3 / F9):\n"
        + "\n".join(violations)
    )
