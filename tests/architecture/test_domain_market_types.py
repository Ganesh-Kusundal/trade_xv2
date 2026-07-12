"""Streaming must use domain MarketTick — no parallel application tick class."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = PROJECT_ROOT / "src" / "application" / "streaming" / "orchestrator.py"
TICK_ROUTER = PROJECT_ROOT / "src" / "application" / "streaming" / "tick_router.py"


def test_orchestrator_reexports_domain_market_tick() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    assert "from domain.entities.market import MarketTick" in text
    tree = ast.parse(text)
    class_names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "MarketTick"
    ]
    assert class_names == [], "application.streaming.orchestrator must not define MarketTick"


def test_tick_router_normalizes_domain_market_tick() -> None:
    text = TICK_ROUTER.read_text(encoding="utf-8")
    assert "from domain.entities.market import MarketTick" in text
    assert "application.streaming.orchestrator import MarketTick" not in text
