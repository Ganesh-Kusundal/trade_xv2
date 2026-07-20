"""Integration test conftest — registers fixtures for all integration tests."""

from __future__ import annotations

import pytest

from tests.e2e.fixtures.event_capturer import EventCapturer


@pytest.fixture
def event_bus_with_capturer(event_bus):
    """Provide an EventBus paired with an EventCapturer for verification.

    Returns a tuple of (event_bus, capturer) where the capturer
    is ready to capture events. Tests should call capturer.subscribe() with
    the event types they want to verify.
    """
    capturer = EventCapturer(event_bus=event_bus)
    return event_bus, capturer
