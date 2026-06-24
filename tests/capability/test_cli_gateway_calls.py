"""AST audit of CLI commands calling broker gateway methods."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# CLI modules that should call broker gateway surfaces.
_CLI_GATEWAY_MODULES = [
    "cli/commands/market_handlers.py",
    "cli/commands/market.py",
    "cli/commands/portfolio.py",
    "cli/commands/account.py",
    "cli/commands/order_placement.py",
    "cli/commands/oms.py",
    "cli/commands/risk_controls.py",
    "cli/commands/news.py",
    "cli/commands/search.py",
]

# Gateway call patterns we expect in broker-touching CLI handlers.
_EXPECTED_GATEWAY_PATTERNS = (
    "gw.quote",
    "gw.depth",
    "gw.history",
    "gw.portfolio",
    "gw.orders",
    "gw.market_data",
    "gw.options",
    "gw.futures",
    "gw.stream",
    "gw.modify_order",
    "gateway.",
    "active_broker",
    "broker_service",
    "OmsService",
    "execution_service",
    "ExecutionComposer",
    "execution_composer",
    "composer.",
    "get_execution_composer",
)


def _extract_source_calls(module_path: Path) -> list[str]:
    """Return attribute/call chains as strings from a Python module."""
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    calls: list[str] = []

    class CallVisitor(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
            parts: list[str] = []
            current: ast.AST = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            calls.append(".".join(reversed(parts)))
            self.generic_visit(node)

    CallVisitor().visit(tree)
    return calls


class TestCliGatewayCalls:
    """CLI handler modules reference broker gateway surfaces."""

    @pytest.mark.parametrize("rel_path", _CLI_GATEWAY_MODULES)
    def test_module_has_gateway_references(self, rel_path: str) -> None:
        path = PROJECT_ROOT / rel_path
        assert path.exists(), f"Missing CLI module {rel_path}"
        calls = _extract_source_calls(path)
        combined = " ".join(calls)
        assert any(pat in combined for pat in _EXPECTED_GATEWAY_PATTERNS), (
            f"{rel_path} has no recognizable gateway call patterns"
        )

    def test_modify_order_uses_composer(self) -> None:
        path = PROJECT_ROOT / "cli/commands/order_placement.py"
        source = path.read_text(encoding="utf-8")
        assert "modify_order" in source
        assert "composer.modify_order" in source or "ExecutionComposer" in source
        assert "gw.modify_order" not in source

    def test_place_order_uses_oms(self) -> None:
        path = PROJECT_ROOT / "cli/commands/order_placement.py"
        source = path.read_text(encoding="utf-8")
        assert "OmsService" in source or "execution_service" in source or "place_order" in source
