"""R2: domain.ports.async_bridge must not import runtime (composition injects runners)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASYNC_BRIDGE = ROOT / "src" / "domain" / "ports" / "async_bridge.py"


def test_async_bridge_has_no_runtime_import() -> None:
    tree = ast.parse(ASYNC_BRIDGE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            if isinstance(node, ast.Import):
                roots = [n.name.split(".")[0] for n in node.names]
            else:
                roots = [node.module.split(".")[0]] if node.module else []
            assert "runtime" not in roots, (
                f"async_bridge must not import runtime (line {node.lineno}); "
                "wire via set_async_runner() at composition root"
            )
