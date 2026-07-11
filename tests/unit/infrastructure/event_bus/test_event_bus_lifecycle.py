"""TOS-P7-003 — EventBus alerting ManagedService wrapper."""

from __future__ import annotations

from infrastructure.event_bus.event_bus import EventBus, EventBusAlertingService


def test_as_managed_service_start_stop_without_engine():
    bus = EventBus()
    svc = bus.as_managed_service()
    assert isinstance(svc, EventBusAlertingService)
    assert svc.name == "event_bus_alerting"
    svc.start()  # no-op without engine
    svc.stop()
    health = svc.health()
    assert health.service == "event_bus_alerting"
