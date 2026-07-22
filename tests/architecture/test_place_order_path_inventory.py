"""Architecture ratchet — place_order spine consolidation (G-P0-3).

Tiers:
  SPINE       — order_manager + execution_engine + spine helper (internal)
  APPLICATION — composer, oms_backtest_adapter, place_order_use_case (via execute)
  INTERFACE   — API/CLI facades (must delegate, not bypass OMS)
  BROKER_WIRE — broker transport (allowed; not application entry)
  DOMAIN_PORT — protocol stubs only
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

_SCAN_ROOTS = (
    "src/application",
    "src/interface/api",
    "src/interface/ui",
    "src/tradex",
    "src/domain",
    "src/brokers",
    "src/runtime",
)

# Application + interface surfaces (excludes broker wire and domain protocol stubs).
_APPLICATION_INTERFACE_ALLOWLIST = frozenset(
    {
        "src/application/oms/order_manager.py",
        "src/application/execution/execution_engine.py",
        "src/application/execution/oms_backtest_adapter.py",
        "src/application/composer/execution.py",
        "src/interface/api/routers/orders.py",
        "src/interface/ui/commands/order_placement.py",
        "src/interface/ui/services/cli_broker_facade.py",
        "src/interface/ui/services/broker_service.py",
    }
)

# Broker wire + domain protocol — tracked separately, not spine violations.
_BROKER_WIRE_ALLOWLIST = frozenset(
    {
        "src/brokers/gateway.py",
        "src/brokers/providers/paper/execution_provider.py",
        "src/brokers/providers/paper/paper_gateway.py",
        "src/brokers/providers/paper/paper_orders.py",
        "src/brokers/providers/upstox/gateway.py",
        "src/brokers/providers/upstox/mutual_funds/adapter.py",
        "src/brokers/providers/upstox/mutual_funds/client.py",
        "src/brokers/providers/upstox/adapters/order_gateway.py",
        "src/brokers/providers/upstox/adapters/upstox_orders.py",
        "src/brokers/providers/upstox/orders/order_command_adapter.py",
        "src/brokers/providers/dhan/gateway.py",
        "src/brokers/providers/dhan/execution/orders.py",
        "src/brokers/providers/dhan/execution/order_placement.py",
        "src/brokers/providers/dhan/api/transport.py",
        "src/brokers/providers/dhan/wire.py",
        "src/brokers/providers/dhan/adapters/order_gateway.py",
        "src/brokers/providers/upstox/wire.py",
        "src/brokers/services/orders.py",
    }
)

_DOMAIN_PROTOCOL_ALLOWLIST = frozenset(
    {
        "src/domain/ports/broker_execution_port.py",
        "src/domain/ports/broker_gateway.py",
        "src/domain/ports/protocols.py",
        "src/domain/repositories/order_repository.py",
        "src/domain/services/orders.py",
        "src/application/oms/protocols.py",
    }
)

_FULL_ALLOWLIST = (
    _APPLICATION_INTERFACE_ALLOWLIST | _BROKER_WIRE_ALLOWLIST | _DOMAIN_PROTOCOL_ALLOWLIST
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
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "place_order":
            return True
    return False


@pytest.mark.unit
def test_place_order_surfaces_are_allowlisted() -> None:
    """No new production place_order without conscious allowlist update."""
    found: set[str] = set()
    for path in _iter_py_files():
        if _defines_place_order(path):
            found.add(path.relative_to(ROOT).as_posix())

    unexpected = sorted(found - _FULL_ALLOWLIST)
    assert not unexpected, (
        "New place_order surfaces — route through spine or update allowlist:\n  "
        + "\n  ".join(unexpected)
    )


@pytest.mark.unit
def test_application_interface_allowlist_is_minimal() -> None:
    """Application/interface tier should stay small (constitution G-P0-3)."""
    assert len(_APPLICATION_INTERFACE_ALLOWLIST) <= 8, (
        "Shrink application/interface allowlist before adding entries"
    )


@pytest.mark.unit
def test_spine_module_exists() -> None:
    path = ROOT / "src/application/execution/spine.py"
    assert path.is_file()
    assert "place_order_spine" in path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_composer_routes_through_spine() -> None:
    text = (ROOT / "src/application/composer/execution.py").read_text(encoding="utf-8")
    assert "place_order_spine" in text


@pytest.mark.unit
def test_cli_facade_uses_runtime_engine() -> None:
    text = (ROOT / "src/interface/ui/services/cli_broker_facade.py").read_text(encoding="utf-8")
    assert "build_execution_engine" in text


@pytest.mark.unit
def test_place_order_use_case_exists() -> None:
    path = ROOT / "src/application/execution/place_order_use_case.py"
    assert path.is_file()
    assert "class PlaceOrderUseCase" in path.read_text(encoding="utf-8")
