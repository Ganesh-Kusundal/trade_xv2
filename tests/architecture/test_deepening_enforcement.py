"""Architecture enforcement tests for deepening roadmap."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_ALIAS_MODULES = {
    "brokers/common/core/exchange_segments.py",
    "brokers/dhan/segments.py",
    "brokers/upstox/instruments/segment_mapper.py",
}


def _iter_py_files(*roots: str):
    for root in roots:
        base = REPO_ROOT / root
        for path in base.rglob("*.py"):
            if "/tests/" in str(path) or path.name.startswith("test_"):
                continue
            yield path


def test_no_inline_exchange_alias_dicts_outside_adapters():
    forbidden_keys = {'"NSE": ExchangeSegment', '"MCX": ExchangeSegment', '"NFO": ExchangeSegment'}
    violations: list[str] = []
    for path in _iter_py_files("brokers", "cli", "datalake"):
        rel = str(path.relative_to(REPO_ROOT))
        if rel in ALLOWED_ALIAS_MODULES:
            continue
        text = path.read_text(encoding="utf-8")
        if any(key in text for key in forbidden_keys):
            violations.append(rel)
    assert not violations, f"Inline exchange alias dicts found: {violations[:5]}"


def test_dhan_domain_has_no_static_canonical_reexports():
    domain_path = REPO_ROOT / "brokers/dhan/domain.py"
    tree = ast.parse(domain_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "brokers.common.core.domain":
            for alias in node.names:
                assert alias.name in {"IST_OFFSET"}, (
                    f"Static re-export {alias.name} violates ADR-001; use __getattr__ shim"
                )


def test_order_manager_documents_orchestration_contract():
    om_path = REPO_ROOT / "application/oms/order_manager.py"
    text = om_path.read_text(encoding="utf-8")
    assert "Orchestration contract" in text
    assert "_internal" in text


def test_api_orders_router_uses_oms_submit_fn():
    orders_path = REPO_ROOT / "api/routers/orders.py"
    text = orders_path.read_text(encoding="utf-8")
    assert "order_manager.place_order" in text or "execution_svc.place_order" in text
    assert "execution_service" in text or "submit_fn" in text


def test_broker_service_exposes_oms_transport_submit():
    svc_path = REPO_ROOT / "cli/services/broker_service.py"
    text = svc_path.read_text(encoding="utf-8")
    assert "ExecutionService" in text
    assert "place_order_through_oms" in text
    assert "execution_service" in text


def test_no_broker_specific_constants_in_common_package():
    """REF-4: UPSTOX operational constants belong in adapter packages."""
    constants_path = REPO_ROOT / "domain/constants/__init__.py"
    text = constants_path.read_text(encoding="utf-8")
    assert "UPSTOX_DEFAULT_RATE_PER_SECOND" not in text
    assert "UPSTOX_WS_PING_INTERVAL_SECONDS" not in text
    assert "UPSTOX_INSTRUMENT_CACHE_HOURS" not in text


def test_market_symbols_fixture_exists():
    fixture = REPO_ROOT / "tests/fixtures/market_symbols.py"
    assert fixture.is_file()
    content = fixture.read_text(encoding="utf-8")
    assert "SYMBOL_RELIANCE" in content
    assert "EXCHANGE_NSE_EQ" in content
