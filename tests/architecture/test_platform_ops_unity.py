"""TRANS-P4-010 — verify/certify/doctor share one platform_ops module."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = "brokers.platform_ops"


def _imports_platform_ops(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _CANONICAL:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _CANONICAL:
                    return True
    return False


@pytest.mark.architecture
def test_broker_ops_uses_platform_ops() -> None:
    path = REPO_ROOT / "src" / "interface" / "ui" / "services" / "broker_ops.py"
    assert _imports_platform_ops(path)


@pytest.mark.architecture
def test_mcp_tools_uses_platform_ops() -> None:
    path = REPO_ROOT / "src" / "brokers" / "mcp" / "tools.py"
    assert _imports_platform_ops(path)


@pytest.mark.architecture
def test_broker_cli_uses_platform_ops() -> None:
    path = REPO_ROOT / "src" / "brokers" / "cli" / "broker.py"
    assert _imports_platform_ops(path)