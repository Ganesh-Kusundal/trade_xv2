"""Event bus fixtures for integration tests.

Provides EventBus + EventCapturer combinators for verifying event flows
in OMS and broker integration tests.
"""

from __future__ import annotations

import pytest

from brokers.common.event_bus import EventBus
from brokers.common.event_bus.dead_letter_queue import DeadLetterQueue
from brokers.common.observability.event_metrics import EventMetrics
from tests.e2e.fixtures.event_capturer import EventCapturer


@pytest.fixture
def event_bus():
    """Provide a fresh EventBus instance with metrics and DLQ.

    Returns an EventBus configured with:
    - EventMetrics for tracking publish/subscribe statistics
    - DeadLetterQueue (max_size=1000) for capturing failed handler events
    """
    metrics = EventMetrics()
    dlq = DeadLetterQueue(max_size=1000)
    return EventBus(metrics=metrics, dead_letter_queue=dlq)


@pytest.fixture
def event_bus_with_capturer(event_bus):
    """Provide an EventBus paired with an EventCapturer for verification.

    This fixture returns a tuple of (event_bus, capturer) where the capturer
    is ready to capture events. Tests should call capturer.subscribe() with
    the event types they want to verify.

    Usage:
        def test_order_flow(event_bus_with_capturer):
            event_bus, capturer = event_bus_with_capturer
            capturer.subscribe("ORDER_PLACED", "TRADE_APPLIED")
            # ... trigger order placement ...
            assert capturer.count("ORDER_PLACED") == 1
    """
    capturer = EventCapturer(event_bus=event_bus)
    return event_bus, capturer


@pytest.fixture
def event_bus_with_all_capture(event_bus):
    """Provide an EventBus with capturer subscribed to all common event types.

    Automatically subscribes the capturer to:
    - ORDER_PLACED
    - ORDER_UPDATED
    - ORDER_CANCELLED
    - TRADE_APPLIED
    - POSITION_UPDATED
    - RISK_CHECK_PASSED
    - RISK_CHECK_FAILED

    Usage:
        def test_full_event_chain(event_bus_with_all_capture):
            event_bus, capturer = event_bus_with_all_capture
            # ... trigger trading flow ...
            assert capturer.count("ORDER_PLACED") >= 1
            assert capturer.count("TRADE_APPLIED") >= 1
    """
    capturer = EventCapturer(event_bus=event_bus)
    capturer.subscribe(
        "ORDER_PLACED",
        "ORDER_UPDATED",
        "ORDER_CANCELLED",
        "TRADE_APPLIED",
        "POSITION_UPDATED",
        "RISK_CHECK_PASSED",
        "RISK_CHECK_FAILED",
    )
    return event_bus, capturer


@pytest.fixture
def dead_letter_queue(event_bus):
    """Provide direct access to the EventBus's DeadLetterQueue.

    Useful for testing error handling and failed event scenarios.
    """
    return event_bus.dead_letter_queue
