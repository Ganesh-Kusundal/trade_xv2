"""TOS-P5-021 — single order-placement spine via OMS OrderManager + ledger outbox."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
ORDER_MANAGER = SRC / "application" / "oms" / "order_manager.py"
ORDER_LIFECYCLE = SRC / "application" / "oms" / "_internal" / "order_lifecycle.py"
SESSION_BRIDGE = SRC / "application" / "oms" / "session_bridge.py"


@pytest.mark.architecture
def test_order_lifecycle_records_intent_before_submit() -> None:
    text = ORDER_LIFECYCLE.read_text(encoding="utf-8")
    assert "record_intent" in text
    assert "ledger_authority_enabled" in text


@pytest.mark.architecture
def test_order_manager_place_order_delegates_to_lifecycle() -> None:
    text = ORDER_MANAGER.read_text(encoding="utf-8")
    assert "def place_order" in text
    assert "submit_to_broker" in text
    assert "record_and_publish" in text


@pytest.mark.architecture
def test_session_bridge_routes_through_order_manager() -> None:
    text = SESSION_BRIDGE.read_text(encoding="utf-8")
    assert "OrderManager" in text
    assert "place_order" in text
    assert "submit_fn" in text


@pytest.mark.architecture
def test_no_parallel_place_order_god_paths_in_application() -> None:
    """application/ must not define alternate place_order that bypasses OMS."""
    forbidden_modules = []
    oms_place = {"application/oms/order_manager.py", "application/oms/session_bridge.py"}
    for path in (SRC / "application").rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in oms_place or "/tests/" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "place_order":
                # Allow Protocol methods and thin wrappers that call OMS.
                text = path.read_text(encoding="utf-8")
                if "OrderManager" in text or "_oms.place_order" in text or "order_manager" in text:
                    continue
                if "Protocol" in text and rel.endswith("protocols.py"):
                    continue
                forbidden_modules.append(rel)
    assert not forbidden_modules, (
        "place_order outside OMS spine (TOS-P5-021):\n" + "\n".join(forbidden_modules)
    )
