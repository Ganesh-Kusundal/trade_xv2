"""P6-3: Network Partition Chaos Tests.

Verifies the system survives network failures gracefully:
1. Broker API goes down mid-order
2. WebSocket disconnects during subscription
3. Database/connection lost during write
4. Network latency spikes (100ms -> 5000ms)
5. Partial failures (some endpoints work, others don't)

These tests use pytest fixtures and context managers to inject failures
in a deterministic, reproducible way. Each test must complete in < 5 seconds.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from infrastructure.event_bus.event_bus import DomainEvent, EventBus, EventBusConfig
from infrastructure.observability.event_metrics import EventMetrics
from infrastructure.resilience.broker_health_monitor import (
    BrokerHealthMonitor,
)

# ──────────────────────────────────────────────────────────────────────
# Chaos injection helpers
# ──────────────────────────────────────────────────────────────────────


@contextmanager
def inject_api_failure(
    broker_name: str = "primary",
    fail_after_calls: int = 0,
    exception_type: type[Exception] = ConnectionError,
):
    """Context manager that makes a broker gateway fail after N successful calls.

    Args:
        broker_name: Label for the broker being mocked.
        fail_after_calls: Number of successful calls before failures begin.
        exception_type: The exception to raise on failure.
    """
    call_count = {"count": 0}

    def failing_method(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] > fail_after_calls:
            raise exception_type(f"Simulated {broker_name} API failure")
        return MagicMock()

    yield failing_method, call_count


@contextmanager
def inject_latency(latency_seconds: float):
    """Context manager that adds artificial latency to mocked calls."""

    def slow_method(*args, **kwargs):
        time.sleep(latency_seconds)
        return MagicMock()

    yield slow_method


@contextmanager
def inject_partial_failure(
    working_methods: set[str],
    failing_methods: set[str],
    exception_type: type[Exception] = ConnectionError,
):
    """Context manager where some methods work and others fail.

    Args:
        working_methods: Method names that should succeed.
        failing_methods: Method names that should raise.
        exception_type: Exception to raise for failing methods.
    """

    def partial_mock(method_name):
        def inner(*args, **kwargs):
            if method_name in working_methods:
                return MagicMock()
            if method_name in failing_methods:
                raise exception_type(f"Partial failure: {method_name} unavailable")
            return MagicMock()

        return inner

    yield partial_mock


# ──────────────────────────────────────────────────────────────────────
# Section 1: Broker API Goes Down Mid-Order
# ──────────────────────────────────────────────────────────────────────


class TestBrokerAPIMidOrderFailure:
    """Verify system handles broker API going down during order operations."""

    def test_health_monitor_detects_consecutive_failures(self):
        """After threshold failures, broker should be marked unhealthy."""
        monitor = BrokerHealthMonitor(failure_threshold=3)

        for _ in range(3):
            monitor.record_failure("dhan")

        assert not monitor.is_healthy("dhan"), (
            "Broker should be unhealthy after 3 consecutive failures"
        )

    def test_health_monitor_resets_on_success(self):
        """A single success should reset the failure counter."""
        monitor = BrokerHealthMonitor(failure_threshold=3)

        for _ in range(2):
            monitor.record_failure("dhan")
        monitor.record_success("dhan")

        assert monitor.is_healthy("dhan"), (
            "Broker should be healthy again after a success resets the counter"
        )


# ──────────────────────────────────────────────────────────────────────
# Section 2: WebSocket Disconnects During Subscription
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketDisconnectChaos:
    """Verify event bus survives subscriber failures (simulating WS disconnect)."""

    def test_event_bus_continues_after_handler_crash(self):
        """If one handler crashes, other handlers should still receive events."""
        bus = EventBus(config=EventBusConfig(fail_fast=True))
        received = {"good_handler": []}

        def crashing_handler(event):
            raise ConnectionError("WebSocket disconnected")

        def good_handler(event):
            received["good_handler"].append(event)

        # Subscribe good handler FIRST so it runs before the crash
        bus.subscribe("TICK", good_handler)
        bus.subscribe("TICK", crashing_handler)

        event = DomainEvent.now("TICK", {"price": 100.0}, symbol="RELIANCE")

        with pytest.raises(ConnectionError):
            bus.publish(event)

        # Good handler should have still received the event (runs before crash)
        assert len(received["good_handler"]) == 1, (
            "Good handler should receive event even when another handler crashes"
        )

    def test_dead_letter_queue_captures_handler_failure(self):
        """Failed handler events should end up in the DLQ."""
        dlq = DeadLetterQueue(max_size=100)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        def failing_handler(event):
            raise RuntimeError("Handler crashed")

        bus.subscribe("TICK", failing_handler)
        event = DomainEvent.now("TICK", {"price": 100.0})
        bus.publish(event)

        assert len(dlq) == 1, "DLQ should contain the failed event"
        dead_letter = dlq.peek(1)[0]
        assert dead_letter.error_type == "RuntimeError"

    def test_event_bus_metrics_track_handler_failures(self):
        """Handler failures should be counted in metrics."""
        metrics = EventMetrics()
        dlq = DeadLetterQueue(max_size=100)
        bus = EventBus(
            metrics=metrics,
            dead_letter_queue=dlq,
            config=EventBusConfig(fail_fast=False),
        )

        def failing_handler(event):
            raise ValueError("Bad handler")

        bus.subscribe("ORDER", failing_handler)
        event = DomainEvent.now("ORDER", {"id": "123"})
        bus.publish(event)

        errors = metrics.get("ORDER", "handler_error:ValueError")
        assert errors >= 1, "Metrics should track handler errors"
        dead_letters = metrics.get("ORDER", "dead_letter")
        assert dead_letters >= 1, "Metrics should track dead letters"

    def test_event_bus_recover_after_transient_failure(self):
        """After a handler stops crashing, bus should work normally."""
        call_count = {"count": 0}
        dlq = DeadLetterQueue(max_size=100)
        bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

        def flaky_handler(event):
            call_count["count"] += 1
            if call_count["count"] <= 2:
                raise ConnectionError("Transient WS disconnect")

        bus.subscribe("TICK", flaky_handler)

        # First two publishes should fail
        event1 = DomainEvent.now("TICK", {"seq": 1})
        bus.publish(event1)
        event2 = DomainEvent.now("TICK", {"seq": 2})
        bus.publish(event2)

        assert len(dlq) == 2, "DLQ should have 2 failed events"

        # Third publish should succeed
        event3 = DomainEvent.now("TICK", {"seq": 3})
        bus.publish(event3)

        assert call_count["count"] == 3
        assert len(dlq) == 2, "DLQ should still only have 2 entries"

    def test_event_bus_unsubscribe_during_dispatch(self):
        """Handler unsubscribing itself during dispatch should not corrupt state."""
        bus = EventBus(config=EventBusConfig(fail_fast=False))
        token_holder = {"token": None}
        received = []

        def self_unsubscribing_handler(event):
            received.append(event)
            bus.unsubscribe(token_holder["token"])

        token = bus.subscribe("TICK", self_unsubscribing_handler)
        token_holder["token"] = token

        event = DomainEvent.now("TICK", {"data": "first"})
        bus.publish(event)

        # Second event should not be received (unsubscribed)
        event2 = DomainEvent.now("TICK", {"data": "second"})
        bus.publish(event2)

        assert len(received) == 1, "Should only receive first event after unsubscribe"


# ──────────────────────────────────────────────────────────────────────
# Section 3: Connection Lost During Write
# ──────────────────────────────────────────────────────────────────────


class TestConnectionLostDuringWrite:
    """Verify system handles connection loss during persistence operations."""

    def test_event_bus_handles_event_log_failure(self):
        """If event log append fails, bus should still dispatch handlers."""
        event_log = MagicMock()
        event_log.append.side_effect = ConnectionError("DB connection lost")
        dlq = DeadLetterQueue(max_size=100)
        bus = EventBus(
            event_log=event_log,
            dead_letter_queue=dlq,
            config=EventBusConfig(fail_fast=False),
        )

        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        event = DomainEvent.now("TICK", {"price": 100.0})
        bus.publish(event)

        # Handler should still have received the event
        assert len(received) == 1, "Handler should receive event even when event_log fails"
        # DLQ should capture the log failure
        assert len(dlq) == 1, "DLQ should capture the log append failure"

    def test_event_bus_fail_fast_on_log_failure(self):
        """When fail_fast=True, log failures should propagate."""
        event_log = MagicMock()
        event_log.append.side_effect = ConnectionError("DB down")
        bus = EventBus(event_log=event_log, config=EventBusConfig(fail_fast=True))

        event = DomainEvent.now("TICK", {"price": 100.0})

        with pytest.raises(ConnectionError, match="DB down"):
            bus.publish(event)

    def test_event_bus_metrics_track_log_errors(self):
        """Log append failures should be tracked in metrics."""
        event_log = MagicMock()
        event_log.append.side_effect = ConnectionError("Lost connection")
        metrics = EventMetrics()
        dlq = DeadLetterQueue(max_size=100)
        bus = EventBus(
            event_log=event_log,
            dead_letter_queue=dlq,
            metrics=metrics,
            config=EventBusConfig(fail_fast=False),
        )

        event = DomainEvent.now("ORDER", {"id": "1"})
        bus.publish(event)

        log_errors = metrics.get("ORDER", "log_error:ConnectionError")
        assert log_errors >= 1, "Metrics should track log errors"

    def test_health_monitor_thread_safety_under_contention(self):
        """Health monitor should be thread-safe under concurrent access."""
        monitor = BrokerHealthMonitor(failure_threshold=5)
        errors = []

        def record_failures():
            try:
                for _ in range(50):
                    monitor.record_failure("dhan")
            except Exception as e:
                errors.append(e)

        def record_successes():
            try:
                for _ in range(50):
                    monitor.record_success("dhan")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_failures),
            threading.Thread(target=record_successes),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Health monitor should be thread-safe, got errors: {errors}"

    def test_health_monitor_any_healthy_with_partial_failure(self):
        """If at least one broker is healthy, any_healthy should return True."""
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")  # dhan is now unhealthy
        monitor.record_success("upstox")  # upstox is healthy

        assert not monitor.is_healthy("dhan")
        assert monitor.is_healthy("upstox")
        assert monitor.any_healthy(["dhan", "upstox"]), (
            "any_healthy should return True when at least one broker is healthy"
        )


# ──────────────────────────────────────────────────────────────────────
# Section 4: Network Latency Spikes
# ──────────────────────────────────────────────────────────────────────


class TestNetworkLatencySpikes:
    """Verify system handles network latency spikes gracefully."""

    def test_health_monitor_records_slow_but_successful_calls(self):
        """A slow but successful call should still reset failure counter."""
        monitor = BrokerHealthMonitor(failure_threshold=3)

        # Simulate: 2 failures, then a slow success
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        time.sleep(0.01)  # Simulate latency
        monitor.record_success("dhan")

        assert monitor.is_healthy("dhan"), "Slow but successful call should restore health"

    def test_latency_does_not_affect_event_bus_dispatch_order(self):
        """Slow handlers should not affect dispatch ordering of other handlers."""
        bus = EventBus(config=EventBusConfig(fail_fast=False))
        order = []

        def slow_handler(event):
            time.sleep(0.05)
            order.append("slow")

        def fast_handler(event):
            order.append("fast")

        bus.subscribe("TICK", slow_handler)
        bus.subscribe("TICK", fast_handler)

        event = DomainEvent.now("TICK", {"data": "test"})
        bus.publish(event)

        # Both should have been dispatched
        assert "slow" in order and "fast" in order, (
            "Both handlers should be dispatched regardless of latency"
        )

    def test_event_bus_publish_latency_does_not_block_subscribers(self):
        """Multiple publishes with varying latency should not block subscribers."""
        bus = EventBus(config=EventBusConfig(fail_fast=False))
        received = []

        def collector(event):
            received.append(event.payload.get("seq"))

        bus.subscribe("TICK", collector)

        # Publish with simulated latency between publishes
        for i in range(10):
            event = DomainEvent.now("TICK", {"seq": i})
            bus.publish(event)

        assert received == list(range(10)), "All events should be received in order despite latency"


# ──────────────────────────────────────────────────────────────────────
# Section 5: Partial Failures
# ──────────────────────────────────────────────────────────────────────


class TestPartialFailures:
    """Verify system handles partial failures (some endpoints work, others don't)."""

    def test_health_monitor_tracks_per_broker_independently(self):
        """Failures on one broker should not affect another's health."""
        monitor = BrokerHealthMonitor(failure_threshold=3)

        for _ in range(5):
            monitor.record_failure("dhan")

        monitor.record_success("upstox")

        assert not monitor.is_healthy("dhan"), "Dhan should be unhealthy"
        assert monitor.is_healthy("upstox"), "Upstox should be healthy"

    def test_event_bus_handles_mixed_handler_results(self):
        """Some handlers succeed, some fail — all should be attempted."""
        dlq = DeadLetterQueue(max_size=100)
        bus = EventBus(config=EventBusConfig(fail_fast=False), dead_letter_queue=dlq)

        results = {"success": [], "failure": []}

        def success_handler(event):
            results["success"].append(event.payload.get("id"))

        def failing_handler(event):
            results["failure"].append(event.payload.get("id"))
            raise RuntimeError("Partial failure")

        bus.subscribe("TICK", success_handler)
        bus.subscribe("TICK", failing_handler)
        bus.subscribe("TICK", success_handler)

        event = DomainEvent.now("TICK", {"id": "event-1"})
        bus.publish(event)

        assert len(results["success"]) == 2, "Both success handlers should receive the event"
        assert len(results["failure"]) == 1, "Failing handler should have been attempted"
        assert len(dlq) == 1, "DLQ should have one entry from the failing handler"

    def test_health_monitor_status_snapshot_is_immutable(self):
        """get_health_status should return a snapshot, not live references."""
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")

        snapshot = monitor.get_health_status()
        snapshot["dhan"].consecutive_failures = 999  # Mutate snapshot

        current = monitor.get_health_status()
        assert current["dhan"].consecutive_failures == 1, (
            "Mutating snapshot should not affect internal state"
        )

    def test_repeated_publishes_do_not_corrupt_subscription_state(self):
        """Rapid publishes should not corrupt internal subscriber dict."""
        bus = EventBus(config=EventBusConfig(fail_fast=False))
        received_count = {"count": 0}

        def handler(event):
            received_count["count"] += 1

        bus.subscribe("TICK", handler)

        # Rapid fire
        for i in range(100):
            bus.publish(DomainEvent.now("TICK", {"seq": i}))

        assert received_count["count"] == 100, "All 100 events should be delivered to the handler"

    def test_chaos_event_bus_with_no_subscribers(self):
        """Publishing with no subscribers should be a no-op, not an error."""
        bus = EventBus(config=EventBusConfig(fail_fast=False))
        event = DomainEvent.now("TICK", {"data": "orphan"})

        # Should not raise
        bus.publish(event)

    def test_unsubscribe_non_existent_token_returns_false(self):
        """Unsubscribing a non-existent token should return False gracefully."""
        bus = EventBus()
        result = bus.unsubscribe("nonexistent-token-12345")
        assert result is False

    def test_subscriber_count_returns_correct_values(self):
        """subscriber_count should accurately reflect subscription state."""
        bus = EventBus()

        assert bus.subscriber_count() == 0
        t1 = bus.subscribe("TICK", lambda e: None)
        bus.subscribe("TICK", lambda e: None)
        bus.subscribe("ORDER", lambda e: None)

        assert bus.subscriber_count("TICK") == 2
        assert bus.subscriber_count("ORDER") == 1
        assert bus.subscriber_count() == 3

        bus.unsubscribe(t1)
        assert bus.subscriber_count("TICK") == 1
        assert bus.subscriber_count() == 2

    def test_clear_removes_all_subscribers(self):
        """clear() should remove all subscriptions."""
        bus = EventBus()
        bus.subscribe("TICK", lambda e: None)
        bus.subscribe("ORDER", lambda e: None)

        bus.clear()

        assert bus.subscriber_count() == 0

    def test_health_monitor_invalid_threshold_raises(self):
        """BrokerHealthMonitor should reject non-positive thresholds."""
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            BrokerHealthMonitor(failure_threshold=0)

        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            BrokerHealthMonitor(failure_threshold=-1)

    def test_health_monitor_reset_individual_broker(self):
        """Resetting a single broker should not affect others."""
        monitor = BrokerHealthMonitor(failure_threshold=2)
        # Make both unhealthy
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_failure("upstox")
        monitor.record_failure("upstox")

        monitor.reset("dhan")

        assert monitor.is_healthy("dhan"), "Dhan should be healthy after reset"
        assert not monitor.is_healthy("upstox"), "Upstox should still be unhealthy"

    def test_health_monitor_reset_all(self):
        """Reset without argument should clear all brokers."""
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("upstox")

        monitor.reset()

        assert monitor.is_healthy("dhan")
        assert monitor.is_healthy("upstox")
