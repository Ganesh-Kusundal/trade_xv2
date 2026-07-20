"""Fault injection tests for Dead Letter Queue (DLQ) scenarios.

Priority 5: DLQ processing, monitoring, and replay functionality.

Tests verify failed event capture, replay capability, and monitoring alerts.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from infrastructure.event_bus import DomainEvent, EventBus, EventBusConfig
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_event(event_type: str = "ORDER_PLACED", event_id: str = "evt-1") -> DomainEvent:
    """Create a domain event for testing."""
    return DomainEvent(
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        payload={"order_id": f"ORD-{event_id}", "symbol": "RELIANCE"},
        symbol="RELIANCE",
        event_id=event_id,
        sequence_number=1,
    )


def _make_failing_handler(exception: Exception = RuntimeError("Handler failed")):
    """Create a handler that raises an exception."""

    def handler(event):
        raise exception

    return handler


def _make_dlq(max_size: int = 100, on_drop=None) -> DeadLetterQueue:
    """Create a dead letter queue for testing."""
    return DeadLetterQueue(max_size=max_size, on_drop=on_drop)


# ── Priority 5.1: DLQ Processing ─────────────────────────────────────────


class TestDLQProcessing:
    """Events fail processing and go to DLQ."""

    def test_dlq_captures_failed_events(self):
        """Failed handler invocations captured in DLQ."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        # Subscribe with failing handler
        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish event
        event = _make_event()
        bus.publish(event)

        # DLQ should have captured the failure
        assert len(dlq) == 1

        dead_letter = dlq.peek(1)[0]
        assert dead_letter.event.event_type == "ORDER_PLACED"
        assert dead_letter.error_type == "RuntimeError"
        assert "Handler failed" in dead_letter.error_message

        bus.unsubscribe(token)

    def test_dlq_can_be_replayed(self):
        """DLQ events can be drained and replayed."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        # Publish multiple failing events
        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        for i in range(5):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        assert len(dlq) == 5

        # Drain DLQ
        dead_letters = dlq.drain()
        assert len(dead_letters) == 5

        # DLQ should be empty after drain
        assert len(dlq) == 0

        # Verify all events captured
        event_ids = [dl.event.event_id for dl in dead_letters]
        assert len(event_ids) == 5

        bus.unsubscribe(token)

    def test_dlq_metrics_show_depth(self):
        """DLQ stats show current depth and capacity."""
        dlq = _make_dlq(max_size=10)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish events
        for i in range(5):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        # Check stats
        stats = dlq.stats()
        assert stats["size"] == 5
        assert stats["capacity"] == 10
        assert stats["dropped"] == 0

        bus.unsubscribe(token)

    def test_dlq_respects_max_size(self):
        """DLQ drops oldest events when capacity exceeded."""
        dlq = _make_dlq(max_size=3)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish more events than capacity
        for i in range(5):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        # DLQ should have max 3 events
        assert len(dlq) == 3
        assert dlq.dropped == 2  # 2 events dropped

        # Oldest events should be dropped
        dead_letters = dlq.peek(10)
        event_ids = [dl.event.event_id for dl in dead_letters]
        assert "evt-0" not in event_ids  # Dropped
        assert "evt-1" not in event_ids  # Dropped
        assert "evt-2" in event_ids  # Kept
        assert "evt-3" in event_ids  # Kept
        assert "evt-4" in event_ids  # Kept

        bus.unsubscribe(token)

    def test_dlq_preserves_event_context(self):
        """DLQ preserves full event context for debugging."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler(ValueError("Invalid order")))

        event = DomainEvent(
            event_type="ORDER_PLACED",
            timestamp=datetime.now(timezone.utc),
            payload={
                "order_id": "ORD-evt-debug",
                "symbol": "RELIANCE",
                "extra_context": "debugging info",
            },
            symbol="RELIANCE",
            event_id="evt-debug",
            sequence_number=1,
        )
        bus.publish(event)

        dead_letter = dlq.peek(1)[0]

        # Verify context preserved
        assert dead_letter.event.event_id == "evt-debug"
        assert dead_letter.event.payload.get("extra_context") == "debugging info"
        assert dead_letter.error_type == "ValueError"
        assert "Invalid order" in dead_letter.error_message
        assert dead_letter.traceback is not None

        bus.unsubscribe(token)

    def test_dlq_handles_multiple_event_types(self):
        """DLQ captures failures from different event types."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token1 = bus.subscribe("ORDER_PLACED", _make_failing_handler(RuntimeError("Order error")))
        token2 = bus.subscribe("ORDER_CANCELLED", _make_failing_handler(ValueError("Cancel error")))

        bus.publish(_make_event("ORDER_PLACED", "evt-1"))
        bus.publish(_make_event("ORDER_CANCELLED", "evt-2"))

        assert len(dlq) == 2

        dead_letters = dlq.peek(10)
        event_types = [dl.event.event_type for dl in dead_letters]
        assert "ORDER_PLACED" in event_types
        assert "ORDER_CANCELLED" in event_types

        bus.unsubscribe(token1)
        bus.unsubscribe(token2)

    def test_dlq_thread_safety(self):
        """DLQ handles concurrent pushes safely."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        errors = []

        def failing_handler(event):
            raise RuntimeError("Concurrent failure")

        token = bus.subscribe("ORDER_PLACED", failing_handler)

        def publish_event(event_id):
            try:
                event = _make_event(event_id=f"evt-{event_id}")
                bus.publish(event)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(publish_event, i) for i in range(10)]
            for f in futures:
                f.result(timeout=10)

        # All events should be captured
        assert len(dlq) == 10
        assert len(errors) == 0  # No exceptions

        bus.unsubscribe(token)

    def test_dlq_on_drop_callback(self):
        """DLQ invokes on_drop callback when capacity exceeded."""
        dropped_events = []

        def on_drop(dead_letter):
            dropped_events.append(dead_letter)

        dlq = _make_dlq(max_size=2, on_drop=on_drop)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish events exceeding capacity
        for i in range(4):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        # Should have dropped events
        assert len(dropped_events) > 0
        assert dlq.dropped > 0

        bus.unsubscribe(token)


# ── Priority 5.2: DLQ Monitoring ─────────────────────────────────────────


class TestDLQMonitoring:
    """DLQ depth monitoring and alerting."""

    def test_alert_triggered_on_depth_threshold(self):
        """Alert triggered when DLQ depth exceeds threshold."""
        dlq = _make_dlq()
        alerts_triggered = []

        def check_alerts():
            if len(dlq) > 5:
                alerts_triggered.append(
                    {
                        "type": "DLQ_DEPTH_EXCEEDED",
                        "depth": len(dlq),
                        "threshold": 5,
                    }
                )

        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))
        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish events to exceed threshold
        for i in range(8):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)
            check_alerts()

        # Alert should have been triggered
        assert len(alerts_triggered) > 0
        assert alerts_triggered[0]["depth"] > 5

        bus.unsubscribe(token)

    def test_admin_endpoint_reports_dlq_stats(self):
        """Admin endpoint provides DLQ statistics."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish some events
        for i in range(3):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        # Simulate admin endpoint stats
        stats = {
            "dlq_size": len(dlq),
            "dlq_capacity": dlq.stats()["capacity"],
            "dlq_dropped": dlq.dropped,
        }

        assert stats["dlq_size"] == 3
        assert stats["dlq_capacity"] == 100
        assert stats["dlq_dropped"] == 0

        bus.unsubscribe(token)

    def test_dlq_depth_monitoring_with_clear(self):
        """DLQ depth resets after clear operation."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish events
        for i in range(5):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        assert len(dlq) == 5

        # Clear DLQ
        dlq.clear()

        assert len(dlq) == 0
        assert dlq.dropped == 0

        bus.unsubscribe(token)

    def test_dlq_monitoring_with_concurrent_publishes(self):
        """DLQ monitoring accurate under concurrent publishes."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        def publish_event(event_id):
            event = _make_event(event_id=f"evt-{event_id}")
            bus.publish(event)

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(publish_event, i) for i in range(10)]
            for f in futures:
                f.result(timeout=10)

        # DLQ should have all events
        assert len(dlq) == 10

        # Stats should be accurate
        stats = dlq.stats()
        assert stats["size"] == 10

        bus.unsubscribe(token)

    def test_dlq_replay_does_not_duplicate(self):
        """DLQ replay doesn't create duplicate events."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        successful_events = []

        def successful_handler(event):
            successful_events.append(event.event_id)

        token_fail = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish failing events
        for i in range(3):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        assert len(dlq) == 3

        # Drain DLQ
        dead_letters = dlq.drain()
        assert len(dead_letters) == 3

        # Remove failing handler
        bus.unsubscribe(token_fail)

        # Replay with successful handler
        token_success = bus.subscribe("ORDER_PLACED", successful_handler)

        for dead_letter in dead_letters:
            bus.publish(dead_letter.event)

        # All events should be processed successfully
        assert len(successful_events) == 3

        # DLQ should still be empty (replay succeeded)
        assert len(dlq) == 0

        bus.unsubscribe(token_success)

    def test_dlq_handles_graceful_degradation(self):
        """System continues operating even when DLQ is full."""
        dlq = _make_dlq(max_size=2)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish events exceeding DLQ capacity
        for i in range(10):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)  # Should not raise

        # System should still be operational
        # DLQ should be at capacity
        assert len(dlq) == 2
        assert dlq.dropped == 8

        bus.unsubscribe(token)

    def test_dlq_stats_accurate_after_operations(self):
        """DLQ stats remain accurate after various operations."""
        dlq = _make_dlq(max_size=5)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        # Publish events
        for i in range(8):
            event = _make_event(event_id=f"evt-{i}")
            bus.publish(event)

        # Check stats
        stats = dlq.stats()
        assert stats["size"] == 5  # At capacity
        assert stats["capacity"] == 5
        assert stats["dropped"] == 3

        # Drain and check again
        dlq.drain()
        stats = dlq.stats()
        assert stats["size"] == 0
        assert stats["dropped"] == 3  # Dropped count persists

        bus.unsubscribe(token)

    def test_dlq_dead_letter_to_dict(self):
        """DeadLetter can be serialized to dict for monitoring."""
        dlq = _make_dlq()
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        token = bus.subscribe("ORDER_PLACED", _make_failing_handler())

        event = _make_event(event_id="evt-serializable")
        bus.publish(event)

        dead_letter = dlq.peek(1)[0]
        data = dead_letter.to_dict()

        # Verify all fields present
        assert "event_type" in data
        assert "event_id" in data
        assert "symbol" in data
        assert "handler_id" in data
        assert "error_type" in data
        assert "error_message" in data
        assert "failed_at" in data
        assert "traceback" in data

        bus.unsubscribe(token)
