"""Flow contract stubs — TRANS-P2-015.

Each test maps to a section in ``docs/architecture/FLOWS.md``. Failures are
expected until Phase 5 implementation closes the gaps; stubs prevent doc drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FLOWS = REPO_ROOT / "docs" / "architecture" / "FLOWS.md"
STATE_MACHINES = REPO_ROOT / "docs" / "architecture" / "STATE_MACHINES.md"
ERROR_TAXONOMY = REPO_ROOT / "docs" / "architecture" / "ERROR_TAXONOMY.md"


@pytest.mark.architecture
def test_flow_docs_exist() -> None:
    for path in (FLOWS, STATE_MACHINES, ERROR_TAXONOMY):
        assert path.is_file(), f"Missing flow artifact: {path.relative_to(REPO_ROOT)}"


@pytest.mark.architecture
@pytest.mark.parametrize(
    "section_marker",
    [
        "§1 — Startup",
        "§6 — Quote",
        "§7 — Order",
        "§9 — Reconciliation",
        "§11 — Mode",
    ],
)
def test_flows_md_contains_required_sections(section_marker: str) -> None:
    text = FLOWS.read_text(encoding="utf-8")
    assert section_marker in text


@pytest.mark.architecture
def test_upstox_market_data_publishes_tick_to_event_bus() -> None:
    """Contract: UpstoxMarketDataV3Multiplexer publishes TICK when event_bus wired."""
    import inspect

    from brokers.upstox.websocket import market_data_v3

    source = inspect.getsource(market_data_v3.UpstoxMarketDataV3Multiplexer)
    assert "_publish_tick_to_bus" in source
    assert '"TICK"' in source or "'TICK'" in source


@pytest.mark.architecture
@pytest.mark.parametrize(
    "module_path,class_name",
    [
        ("brokers.dhan.websocket.publish", "MarketFeedPublisher"),
        ("brokers.upstox.websocket.market_data_v3", "UpstoxMarketDataV3Multiplexer"),
    ],
)
def test_tick_drop_surfaces_market_data_degraded(module_path: str, class_name: str) -> None:
    """Contract: dropped ticks emit MARKET_DATA_DEGRADED (fail-closed MD-3)."""
    import importlib
    import inspect

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    source = inspect.getsource(cls)
    assert "MARKET_DATA_DEGRADED" in source
    assert "_maybe_emit_market_data_degraded" in source


@pytest.mark.architecture
def test_trading_context_requires_event_bus() -> None:
    """Contract §1: TradingContext fails closed without EventBus."""
    import inspect

    from application.oms import context

    init_src = inspect.getsource(context.TradingContext.__init__)
    assert "requires an event_bus" in init_src
