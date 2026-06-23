"""Event capture utility for verifying event bus flows in E2E tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from infrastructure.event_bus import DomainEvent, EventBus


@dataclass
class EventCapturer:
    """Captures events published to an EventBus for verification.

    Usage:
        capturer = EventCapturer(event_bus)
        capturer.subscribe("ORDER_PLACED", "TRADE_APPLIED")
        # ... trigger some action ...
        assert len(capturer.events("ORDER_PLACED")) == 1
    """

    event_bus: EventBus
    _captured: dict[str, list[DomainEvent]] = field(default_factory=dict)
    _all_events: list[DomainEvent] = field(default_factory=list)

    def subscribe(self, *event_types: str) -> None:
        """Subscribe to specific event types. If none given, capture all."""
        handler = self._make_handler()
        if not event_types:
            # Capture everything by subscribing to a catch-all
            # Note: EventBus doesn't support wildcard, so caller must specify
            raise ValueError("Must specify at least one event type")
        for et in event_types:
            self.event_bus.subscribe(et, handler)
            if et not in self._captured:
                self._captured[et] = []

    def _make_handler(self):
        def handler(event: DomainEvent) -> None:
            self._all_events.append(event)
            if event.event_type in self._captured:
                self._captured[event.event_type].append(event)
        return handler

    def events(self, event_type: str) -> list[DomainEvent]:
        """Get all captured events of a specific type."""
        return list(self._captured.get(event_type, []))

    def all_events(self) -> list[DomainEvent]:
        """Get all captured events."""
        return list(self._all_events)

    def count(self, event_type: str) -> int:
        """Count events of a specific type."""
        return len(self._captured.get(event_type, []))

    def total_count(self) -> int:
        """Total number of captured events."""
        return len(self._all_events)

    def clear(self) -> None:
        """Clear all captured events."""
        for lst in self._captured.values():
            lst.clear()
        self._all_events.clear()

    def assert_event_published(self, event_type: str, min_count: int = 1) -> None:
        """Assert that at least min_count events of the given type were published."""
        count = self.count(event_type)
        assert count >= min_count, (
            f"Expected at least {min_count} '{event_type}' events, but got {count}"
        )

    def assert_event_payload_matches(
        self, event_type: str, expected_keys: dict[str, Any], index: int = 0
    ) -> None:
        """Assert that an event's payload contains expected key-value pairs."""
        events = self.events(event_type)
        assert index < len(events), (
            f"No '{event_type}' event at index {index} (only {len(events)} captured)"
        )
        event = events[index]
        for key, expected_value in expected_keys.items():
            actual = event.payload.get(key)
            assert actual == expected_value, (
                f"Event '{event_type}' payload[{key}] = {actual!r}, expected {expected_value!r}"
            )
