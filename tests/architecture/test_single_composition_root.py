"""WS-G — ProcessKernel is the sole direct caller of wire_* outside allowlist."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

ALLOWLIST = frozenset(
    {
        "runtime/composition.py",
        "runtime/wire_runtime_hooks.py",
        "runtime/kernel.py",
    }
)

FORBIDDEN_SYMBOLS = frozenset({"wire_domain_port_sinks", "wire_runtime_hooks"})


def _references_forbidden_symbol(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            base = alias.name.split(".")[-1]
            if base in FORBIDDEN_SYMBOLS:
                return alias.name
    if isinstance(node, ast.ImportFrom) and node.module:
        for alias in node.names:
            if alias.name in FORBIDDEN_SYMBOLS:
                return f"{node.module}.{alias.name}"
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_SYMBOLS:
            return func.id
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_SYMBOLS:
            return func.attr
    if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_SYMBOLS:
        return node.attr
    return None


@pytest.mark.architecture
def test_single_composition_root_for_wire_helpers() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SRC).as_posix()
        if rel in ALLOWLIST:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            symbol = _references_forbidden_symbol(node)
            if symbol is not None:
                violations.append(f"{rel}:{getattr(node, 'lineno', '?')}: {symbol}")
    assert not violations, (
        "wire_domain_port_sinks / wire_runtime_hooks must be invoked only from "
        "runtime/kernel.py (via ProcessKernel.wire) or allowlisted modules:\n"
        + "\n".join(violations)
    )
