"""TOS-P2-002 / ADR-021 — application/domain must not call wire (symbol, exchange) paths."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
LAYERS = ("application", "domain")
# Heuristic: forbidden direct wire-style calls from app/domain into broker wire modules.
FORBIDDEN_IMPORT_PREFIXES = (
    "brokers.dhan.wire",
    "brokers.upstox.wire",
    "brokers.dhan.api",
    "brokers.upstox.api",
)


@pytest.mark.architecture
def test_application_domain_do_not_import_wire_modules() -> None:
    violations: list[str] = []
    for layer in LAYERS:
        root = SRC / layer
        for path in root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mod = None
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                if not mod:
                    continue
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        violations.append(
                            f"{path.relative_to(SRC)}: imports {mod}"
                        )
    assert not violations, (
        "application/domain import wire modules (ADR-021):\n"
        + "\n".join(violations)
    )
