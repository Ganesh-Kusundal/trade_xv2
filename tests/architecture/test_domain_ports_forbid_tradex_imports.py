"""Domain ports must not import presentation or composition packages."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from domain.events.types import DomainEvent, EventType, canonical_event_types
from infrastructure.event_bus.event_bus import EventBus


def test_domain_broker_adapter_port_does_not_import_tradex() -> None:
    """Domain broker port must not depend upward on tradex."""
    port_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "domain"
        / "ports"
        / "broker_adapter.py"
    )
    tree = ast.parse(port_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tradex"):
            pytest.fail(f"domain.ports.broker_adapter imports tradex: {node.module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tradex"):
                    pytest.fail(f"domain.ports.broker_adapter imports tradex: {alias.name}")


def test_market_bridge_event_types_in_canonical_enum() -> None:
    """Orphan bridge event types must be registered in EventType."""
    canonical = canonical_event_types()
    for name in ("QUOTE", "DEPTH_20", "DEPTH_200", "TRADE_FILLED"):
        assert name in canonical


def test_domain_event_payload_is_immutable_mapping() -> None:
    """DomainEvent freezes top-level payload keys (Phase 0)."""
    event = DomainEvent.now("TICK", {"ltp": 100.0})
    with pytest.raises(TypeError):
        event.payload["ltp"] = 200.0  # type: ignore[index]


def test_event_bus_warns_on_unknown_event_type(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus(enforce_event_types=True)
    event = DomainEvent.now("NOT_A_REAL_EVENT", {"x": 1})
    with caplog.at_level("WARNING"):
        bus.publish(event)
    assert any("unknown event_type" in r.message for r in caplog.records)


def test_tradex_runtime_capabilities_reexports_from_domain() -> None:
    """Capability type is shared via domain.capabilities.broker_capabilities SSOT."""
    import brokers.common.broker_capabilities as bc_cap
    import domain.capabilities.broker_capabilities as dom_cap
    import tradex.runtime.capabilities as tr_cap

    assert tr_cap.BrokerCapabilities is dom_cap.BrokerCapabilities
    assert bc_cap.BrokerCapabilities is dom_cap.BrokerCapabilities
    assert tr_cap.BrokerCapabilities is bc_cap.BrokerCapabilities
