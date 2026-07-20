"""TOS-P5-002 / DR-B4 — interface.ui must not import concrete broker packages."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UI_ROOT = Path(__file__).resolve().parents[2] / "src" / "interface" / "ui"
FORBIDDEN_PREFIXES = ("brokers.dhan", "brokers.upstox", "brokers.paper")


def _module_prefix(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module
    if isinstance(node, ast.Import):
        for alias in node.names:
            return alias.name
    return None


def _forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        mod = _module_prefix(node)
        if not mod:
            continue
        for prefix in FORBIDDEN_PREFIXES:
            if mod == prefix or mod.startswith(prefix + "."):
                hits.append(f"{path.relative_to(UI_ROOT.parent.parent)}: {mod}")
    return hits


@pytest.mark.architecture
def test_interface_ui_has_no_concrete_broker_imports() -> None:
    """UI may use brokers.services / platform_ops, never dhan/upstox/paper packages."""
    violations: list[str] = []
    for path in UI_ROOT.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        violations.extend(_forbidden_imports(path))
    assert not violations, (
        "interface.ui imports concrete broker packages (TOS-P5-002):\n" + "\n".join(violations)
    )


@pytest.mark.architecture
def test_compose_delegates_to_runtime_factory() -> None:
    """CLI/API compose roots must call runtime.factory.build (TOS-P5-001)."""
    import inspect

    import interface.ui.services.compose as compose_mod
    import runtime.api_compose as api_compose

    src = inspect.getsource(compose_mod.build_runtime)
    assert "build(" in src, "build_runtime must call runtime.factory.build"
    assert "TradingRuntimeFactory(" not in src

    api_src = inspect.getsource(api_compose.build_for_api)
    assert "build(" in api_src, "build_for_api must call runtime.factory.build"
    assert "TradingRuntimeFactory(" not in api_src
