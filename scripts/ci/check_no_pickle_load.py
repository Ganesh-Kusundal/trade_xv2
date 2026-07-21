#!/usr/bin/env python3
"""Fail if pickle.load appears outside migration helpers (SEC-01)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

SCAN_DIRS = (SRC / "brokers", SRC / "datalake")


def _pickle_load_violations(path: Path, *, allow_migration: bool) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "load"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "pickle"
        ):
            continue
        if allow_migration:
            is_migration = any(
                isinstance(parent, ast.FunctionDef)
                and parent.lineno <= node.lineno <= parent.end_lineno
                and "migrate" in parent.name.lower()
                for parent in ast.walk(tree)
            )
            if is_migration:
                continue
        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return violations


def main() -> int:
    violations: list[str] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "test" in path.parts:
                continue
            allow_migration = base.name == "brokers"
            violations.extend(_pickle_load_violations(path, allow_migration=allow_migration))

    if violations:
        print("pickle.load violations:\n" + "\n".join(violations[:50]), file=sys.stderr)
        return 1
    print("OK: no pickle.load outside migration helpers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
