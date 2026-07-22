"""P3-T2 (drift D12): document and enforce the single event-bus boundary (ADR-004)."""

from __future__ import annotations

import pytest

from infrastructure.event_bus import AsyncEventBus, EventBus


def test_canonical_event_bus_is_single_implementation():
    """The canonical bus is ``infrastructure.event_bus.EventBus``."""
    assert EventBus is not None
    bus = EventBus()
    assert bus is not None


def test_fast_event_bus_removed():
    """ADR-004: FastEventBus parallel path deleted in Phase 4 R6."""
    with pytest.raises(ModuleNotFoundError):
        import infrastructure.event_bus.fast_event_bus  # noqa: F401


def test_async_event_bus_wraps_canonical_sync_bus():
    """API/async facade delegates to the canonical sync EventBus."""
    sync = EventBus()
    async_bus = AsyncEventBus(sync, max_queue_size=100)
    assert async_bus._bus is sync


def test_event_bus_service_is_injected_facade():
    """EventBusService is a UI facade — it receives the canonical bus."""
    from interface.ui.commands.events import EventBusService

    bus = EventBus()
    svc = EventBusService(event_bus=bus)
    assert svc.event_bus is bus
