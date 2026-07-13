"""C0.9 — baseline inventory of production place_order surfaces.

Tracks fragmentation until Phase 1 collapses to a single spine
(OrderServicePort / PlaceOrderUseCase → OMS). This test fails if new
unexpected modules gain a place_order entry without updating the allowlist.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Production packages scanned (not tests, not venv).
_SCAN_ROOTS = (
    "src/application",
    "src/interface/api",
    "src/interface/ui",
    "src/tradex",
    "src/domain",
    "src/brokers",
    "src/runtime",
)

# Known surfaces as of CODE_REALITY plan (2026-07-10). Shrink over Phase 1.
_ALLOWED_PLACE_ORDER_FILES = frozenset(
    {
        "src/application/oms/protocols.py",
        "src/application/oms/order_repository_adapter.py",
        "src/application/oms/order_manager.py",
        "src/application/composer/execution.py",
        "src/application/execution/execution_service.py",
        "src/application/execution/execution_engine.py",
        "src/application/execution/execution_mode_adapter.py",
        "src/application/execution/place_order_use_case.py",
        "src/interface/api/routers/orders.py",
        "src/interface/api/v2/domain_endpoints.py",
        "src/interface/ui/commands/order_placement.py",
        "src/interface/ui/services/cli_broker_facade.py",
        "src/interface/ui/services/broker_service.py",
        "src/domain/repositories/order_repository.py",
        "src/domain/ports/broker_gateway.py",
        "src/domain/ports/protocols.py",
        "src/domain/services/orders.py",
        "src/brokers/paper/execution_provider.py",
        "src/brokers/paper/paper_gateway.py",
        "src/brokers/paper/paper_orders.py",
        "src/brokers/upstox/gateway.py",
        "src/brokers/upstox/mutual_funds/adapter.py",
        "src/brokers/upstox/mutual_funds/client.py",
        "src/brokers/upstox/adapters/order_gateway.py",
        "src/brokers/upstox/orders/order_command_adapter.py",
        "src/brokers/dhan/gateway.py",
        "src/brokers/dhan/execution/orders.py",
        "src/brokers/dhan/execution/order_placement.py",
        "src/brokers/dhan/api/transport.py",
        # src/brokers/dhan/order_placement.py — removed (shim deleted; logic in execution/order_placement.py)
    }
)


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            s = str(path)
            if "/tests/" in s or s.endswith("_test.py") or "/__pycache__/" in s:
                continue
            if path.name.startswith("test_"):
                continue
            files.append(path)
    return files


def _defines_place_order(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "place_order":
            return True
        if isinstance(node, ast.ClassDef) and node.name in {
            "PlaceOrderUseCase",
            "PlaceOrder",
        }:
            return True
    return False


@pytest.mark.unit
def test_place_order_surfaces_are_allowlisted() -> None:
    """No new production place_order without conscious allowlist update."""
    found: set[str] = set()
    for path in _iter_py_files():
        if _defines_place_order(path):
            rel = path.relative_to(ROOT).as_posix()
            found.add(rel)

    unexpected = sorted(found - _ALLOWED_PLACE_ORDER_FILES)
    missing_tracked = sorted(_ALLOWED_PLACE_ORDER_FILES - found)

    assert not unexpected, (
        "New place_order surfaces found — route them through OMS spine "
        f"or update allowlist deliberately:\n  " + "\n  ".join(unexpected)
    )
    # Soft: files may move; missing allowlist entries are reported but not fatal
    # until Phase 1 shrink. Keep as warning via xfail-style assert soft.
    if missing_tracked:
        # Allow deleted/moved paths: only fail if more than half the allowlist vanished.
        assert len(missing_tracked) < len(_ALLOWED_PLACE_ORDER_FILES) * 0.5, (
            "Many allowlisted place_order files disappeared — refresh allowlist:\n  "
            + "\n  ".join(missing_tracked)
        )


@pytest.mark.unit
def test_place_order_use_case_exists_but_inventory_notes_orphan() -> None:
    """Canonical use case file must exist for Phase 1 adoption."""
    path = ROOT / "src/application/execution/place_order_use_case.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "class PlaceOrderUseCase" in text
