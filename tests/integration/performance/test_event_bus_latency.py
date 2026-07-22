"""Performance latency benchmark for canonical EventBus hot path."""

import time

from domain.events import DomainEvent
from infrastructure.event_bus.event_bus import EventBus, EventBusConfig


def test_event_bus_publish_hot_path_latency_under_500_microseconds():
    """Canonical bus includes DLQ/idempotency hooks — looser than deleted FastEventBus."""
    bus = EventBus(config=EventBusConfig(enforce_event_types=False, logging_enabled=False))
    count = 0

    def on_tick(event: DomainEvent) -> None:
        nonlocal count
        count += 1

    bus.subscribe("TICK", on_tick)

    for i in range(1_000):
        bus.publish(DomainEvent.now("TICK", {"ltp": 2500.00, "warm": i}, symbol="NIFTY"))

    iterations = 20_000
    start = time.perf_counter()
    for i in range(iterations):
        bus.publish(DomainEvent.now("TICK", {"ltp": 2500.00, "i": i}, symbol="NIFTY"))
    elapsed = time.perf_counter() - start

    avg_latency_us = (elapsed / iterations) * 1e6
    print(f"\nEventBus avg publish latency: {avg_latency_us:.2f} µs")

    assert count >= iterations
    assert avg_latency_us < 500.0, f"Hot-path latency too high: {avg_latency_us:.2f} µs"
