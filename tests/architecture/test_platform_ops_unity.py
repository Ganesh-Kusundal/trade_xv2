"""TRANS-P4-010 — verify/certify/doctor share one platform_ops module."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = "brokers.platform_ops"
_INTERFACE_BRIDGE = "runtime.platform_bridge"


def _imports_module(path: Path, module: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    return True
    return False


@pytest.mark.architecture
def test_doctor_uses_platform_ops() -> None:
    path = REPO_ROOT / "src" / "interface" / "ui" / "commands" / "doctor" / "__init__.py"
    assert _imports_module(path, _INTERFACE_BRIDGE) or _imports_module(path, _CANONICAL)


def test_broker_cli_uses_platform_ops() -> None:
    path = REPO_ROOT / "src" / "brokers" / "cli" / "broker.py"
    assert _imports_module(path, _CANONICAL)
