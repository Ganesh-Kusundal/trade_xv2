"""Tests that ResilienceConfig drives concrete collaborator construction (P4)."""

from __future__ import annotations

from runtime.resilience import ResilienceConfig


def test_build_resilient_event_bus_applies_logging_enabled() -> None:
    """Event-log persistence knob from ResilienceConfig reaches the EventBus."""
    from infrastructure.bootstrap import build_resilient_event_bus

    cfg_off = ResilienceConfig(event_log_enabled=False)
    bus_off = build_resilient_event_bus(resilience=cfg_off)
    assert bus_off.logging_enabled is False

    cfg_on = ResilienceConfig(event_log_enabled=True)
    bus_on = build_resilient_event_bus(resilience=cfg_on)
    assert bus_on.logging_enabled is True


def test_build_resilient_event_bus_applies_idempotency_cache_size() -> None:
    """idempotency_ttl_seconds maps to the bus duplicate-suppression cache size."""
    from infrastructure.bootstrap import build_resilient_event_bus

    cfg = ResilienceConfig(idempotency_ttl_seconds=5000)
    bus = build_resilient_event_bus(resilience=cfg)
    # 5000s TTL -> 5000-entry cache (within the [1000, 1_000_000] clamp).
    assert bus._processed_events.maxlen == 5000


def test_build_async_event_bus_applies_queue_size() -> None:
    """AsyncEventBus queue size comes from ResilienceConfig.max_async_bus_queue."""
    from infrastructure.bootstrap import build_async_event_bus, build_event_bus
    from runtime.resilience import ResilienceConfig

    cfg = ResilienceConfig(max_async_bus_queue=2500)
    sync = build_event_bus()
    async_bus = build_async_event_bus(sync, resilience=cfg)
    assert async_bus._max_queue_size == 2500
