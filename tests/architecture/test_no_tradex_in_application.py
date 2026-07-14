"""Application layer must not import tradex (locks in SessionOpenerPort injection)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_application_does_not_import_tradex() -> None:
    violations: list[str] = []
    for path in (ROOT / "src" / "application").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tradex"):
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: from {node.module}"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("tradex"):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: import {alias.name}"
                        )
    assert not violations, (
        "Application layer must not import tradex "
        "(use runtime.session_opener.get_session_opener() instead):\n"
        + "\n".join(violations)
    )
