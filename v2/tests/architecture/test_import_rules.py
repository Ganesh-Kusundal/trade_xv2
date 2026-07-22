"""Domain purity: domain must not import outer layers (stdlib AST scan)."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_DOMAIN = _SRC / "domain"
_FORBIDDEN = ("application", "infrastructure", "runtime", "interface", "plugins")


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_domain_does_not_import_outer_layers() -> None:
    violations: list[str] = []
    for path in sorted(_DOMAIN.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad = _imported_roots(tree) & set(_FORBIDDEN)
        if bad:
            rel = path.relative_to(_SRC)
            violations.append(f"{rel}: imports {sorted(bad)}")
    assert not violations, "domain purity violated:\n" + "\n".join(violations)
