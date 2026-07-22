"""Application must not import concrete broker plugins (composition root only)."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_APP = _SRC / "application"


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_application_does_not_import_plugins() -> None:
    violations: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad = _imported_roots(tree) & {"plugins"}
        if bad:
            rel = path.relative_to(_SRC)
            violations.append(f"{rel}: imports plugins")
    assert not violations, "application→plugins leak:\n" + "\n".join(violations)
