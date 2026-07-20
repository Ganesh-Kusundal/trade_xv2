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


def test_alerting_loop_lives_on_managed_service():
    """GC-01: evaluation loop is owned by EventBusAlertingService, not EventBus."""
    from infrastructure.observability.alerting import AlertingEngine
    from infrastructure.observability.event_metrics import EventMetrics

    bus = EventBus(metrics=EventMetrics(), alerting_engine=AlertingEngine(EventMetrics()))
    svc = bus.as_managed_service()
    assert hasattr(svc, "_alerting_loop")
    assert not hasattr(bus, "_alerting_loop")
