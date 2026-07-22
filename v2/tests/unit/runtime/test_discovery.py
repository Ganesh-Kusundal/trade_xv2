"""Plugin discovery — entry points with fallback explicit register() imports."""

from __future__ import annotations

from domain.enums import BrokerId
from plugins.brokers.registry import register_broker_plugin
from runtime.discovery import discover_brokers


def test_discover_finds_paper_dhan_upstox_after_registers() -> None:
    from plugins.brokers.dhan import register as register_dhan
    from plugins.brokers.upstox import register as register_upstox

    register_dhan()
    register_upstox()

    # Paper owned by B2 — use plugin register when present, else stub for discover contract
    try:
        from plugins.brokers.paper import register as register_paper

        register_paper()
    except ImportError:
        register_broker_plugin(BrokerId.PAPER, {"stub": True})

    found = discover_brokers()
    assert BrokerId.PAPER in found
    assert BrokerId.DHAN in found
    assert BrokerId.UPSTOX in found
