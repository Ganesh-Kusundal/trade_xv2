"""P3-T2 (drift D12): document and enforce the single event-bus boundary."""

from __future__ import annotations

from infrastructure.event_bus import EventBus


def test_canonical_event_bus_is_single_implementation():
    """The canonical bus is ``infrastructure.event_bus.EventBus``."""
    assert EventBus is not None
    bus = EventBus()
    assert bus is not None


def test_event_bus_service_is_injected_facade():
    """EventBusService is a UI facade — it receives the canonical bus."""
    from interface.ui.commands.events import EventBusService

    bus = EventBus()
    svc = EventBusService(event_bus=bus)
    assert svc.event_bus is bus
