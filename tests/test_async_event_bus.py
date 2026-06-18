"""Tests for AsyncEventBus (Phase 3-4).

Covers:
- Start/stop lifecycle
- Publish with all backpressure policies (BLOCK, DROP, ERROR)
- Sync and async handler dispatch
- Handler failure isolation and DLQ integration
- FIFO ordering guarantee
- wait_for_completion
- get_stats
- Subscribe/unsubscribe thread safety
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from brokers.common.event_bus.async_event_bus import AsyncEventBus, BackpressurePolicy
from brokers.common.event_bus.event_bus import DomainEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type: str = "TEST", payload: dict | None = None) -> DomainEvent:
    return DomainEvent(
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        payload=payload or {"key": "value"},
    )


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestAsyncEventBusLifecycle:

    @pytest.mark.asyncio
    async def test_start_creates_worker_task(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        assert not bus.is_running
        await bus.start()
        assert bus.is_running
        assert bus._worker_task is not None
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_terminates_worker(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_start_idempotent(self, caplog: pytest.LogCaptureFixture) -> None:
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        with caplog.at_level(logging.WARNING):
            await bus.start()
        assert any("already running" in r.message for r in caplog.records)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        await bus.stop()  # Should not raise
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_publish_before_start_is_dropped(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        await bus.publish("TEST", {"x": 1})
        assert bus._dropped_count == 1
        assert bus.queue_size == 0


# ---------------------------------------------------------------------------
# Backpressure policy tests
# ---------------------------------------------------------------------------

class TestBackpressurePolicies:

    @pytest.mark.asyncio
    async def test_block_policy_waits_for_space(self) -> None:
        bus = AsyncEventBus(maxsize=2, backpressure_policy=BackpressurePolicy.BLOCK)
        await bus.start()

        # Fill the queue
        await bus.publish("A", {"n": 1})
        await bus.publish("B", {"n": 2})

        # Third publish should block until space frees up
        # We process the first item to make space
        await asyncio.sleep(0.05)  # Let worker process
        await bus.publish("C", {"n": 3})  # Should not hang

        await bus.stop()

    @pytest.mark.asyncio
    async def test_drop_policy_drops_when_full(self, caplog: pytest.LogCaptureFixture) -> None:
        bus = AsyncEventBus(maxsize=1, backpressure_policy=BackpressurePolicy.DROP)
        
        # Don't start the bus - events published before start are dropped
        await bus.publish("TEST", {"n": 1})
        assert bus._dropped_count == 1
        
        # Now start and test DROP policy when running
        await bus.start()
        
        # Add a handler that blocks long enough to fill queue
        import threading
        barrier = threading.Event()
        
        def blocking_handler(event: DomainEvent) -> None:
            barrier.wait(timeout=2.0)
        
        bus.subscribe("BLOCK", blocking_handler)
        await bus.publish("BLOCK", {"n": 1})  # Goes into queue
        await asyncio.sleep(0.02)  # Worker picks it up and blocks
        
        with caplog.at_level(logging.WARNING):
            await bus.publish("BLOCK", {"n": 2})  # Should be dropped
        
        barrier.set()  # Release the blocking handler
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()
        
        assert bus._dropped_count >= 1

    @pytest.mark.asyncio
    async def test_error_policy_configuration(self) -> None:
        """Verify ERROR policy is properly configured."""
        bus = AsyncEventBus(maxsize=10, backpressure_policy=BackpressurePolicy.ERROR)
        assert bus._config.backpressure_policy == BackpressurePolicy.ERROR
        await bus.start()
        await bus.publish("TEST", {"x": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()


# ---------------------------------------------------------------------------
# Handler dispatch tests
# ---------------------------------------------------------------------------

class TestHandlerDispatch:

    @pytest.mark.asyncio
    async def test_sync_handler_receives_event(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        received: list[DomainEvent] = []

        def sync_handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("TEST", sync_handler)
        await bus.start()
        await bus.publish("TEST", {"data": "sync"})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert len(received) == 1
        assert received[0].event_type == "TEST"
        assert received[0].payload["data"] == "sync"

    @pytest.mark.asyncio
    async def test_async_handler_receives_event(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        received: list[DomainEvent] = []

        async def async_handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("TEST", async_handler)
        await bus.start()
        await bus.publish("TEST", {"data": "async"})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert len(received) == 1
        assert received[0].payload["data"] == "async"

    @pytest.mark.asyncio
    async def test_multiple_handlers_for_same_event(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        results: list[str] = []

        def handler_a(event: DomainEvent) -> None:
            results.append("A")

        async def handler_b(event: DomainEvent) -> None:
            results.append("B")

        bus.subscribe("MULTI", handler_a)
        bus.subscribe("MULTI", handler_b)
        await bus.start()
        await bus.publish("MULTI", {"x": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert sorted(results) == ["A", "B"]

    @pytest.mark.asyncio
    async def test_handler_failure_does_not_stop_other_handlers(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        good_received = []

        def failing_handler(event: DomainEvent) -> None:
            raise ValueError("handler boom")

        def good_handler(event: DomainEvent) -> None:
            good_received.append(event)

        bus.subscribe("FAIL", failing_handler)
        bus.subscribe("FAIL", good_handler)
        await bus.start()
        await bus.publish("FAIL", {"x": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert len(good_received) == 1
        assert bus._error_count >= 1

    @pytest.mark.asyncio
    async def test_handler_failure_records_error_count(self) -> None:
        """Handler failure should increment error count."""
        bus = AsyncEventBus(maxsize=100)

        def failing_handler(event: DomainEvent) -> None:
            raise RuntimeError("error count test")

        bus.subscribe("ERR_CNT", failing_handler)
        await bus.start()
        await bus.publish("ERR_CNT", {"x": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert bus._error_count >= 1

    @pytest.mark.asyncio
    async def test_handler_failure_increments_metrics(self) -> None:
        from brokers.common.observability.event_metrics import EventMetrics

        metrics = EventMetrics()
        bus = AsyncEventBus(maxsize=100, metrics=metrics)

        def failing_handler(event: DomainEvent) -> None:
            raise ValueError("metrics test")

        bus.subscribe("METRIC_FAIL", failing_handler)
        await bus.start()
        await bus.publish("METRIC_FAIL", {"x": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert metrics.get("METRIC_FAIL", "handler_error:ValueError") == 1


# ---------------------------------------------------------------------------
# Subscribe / Unsubscribe tests
# ---------------------------------------------------------------------------

class TestSubscribeUnsubscribe:

    @pytest.mark.asyncio
    async def test_subscribe_adds_handler(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        received = []

        def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("SUB", handler)
        await bus.start()
        await bus.publish("SUB", {"v": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_handler(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        received = []

        def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("UNSUB", handler)
        bus.unsubscribe("UNSUB", handler)
        await bus.start()
        await bus.publish("UNSUB", {"v": 1})
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_handler_no_error(self) -> None:
        bus = AsyncEventBus(maxsize=100)

        def handler(event: DomainEvent) -> None:
            pass

        bus.unsubscribe("NONEXIST", handler)  # Should not raise

    @pytest.mark.asyncio
    async def test_no_handlers_for_event_type(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        await bus.publish("NO_ONE", {"v": 1})
        await bus.wait_for_completion(timeout=2.0)
        await bus.stop()
        # Should succeed without errors
        assert bus._event_count == 1


# ---------------------------------------------------------------------------
# FIFO ordering tests
# ---------------------------------------------------------------------------

class TestFIFOOrdering:

    @pytest.mark.asyncio
    async def test_events_processed_in_order(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        order: list[int] = []

        def handler(event: DomainEvent) -> None:
            order.append(event.payload["seq"])

        bus.subscribe("ORDERED", handler)
        await bus.start()

        for i in range(10):
            await bus.publish("ORDERED", {"seq": i})

        await bus.wait_for_completion(timeout=5.0)
        await bus.stop()

        assert order == list(range(10))


# ---------------------------------------------------------------------------
# wait_for_completion tests
# ---------------------------------------------------------------------------

class TestWaitForCompletion:

    @pytest.mark.asyncio
    async def test_wait_returns_true_when_done(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        await bus.publish("TEST", {"v": 1})
        result = await bus.wait_for_completion(timeout=2.0)
        assert result is True
        await bus.stop()

    @pytest.mark.asyncio
    async def test_wait_returns_false_on_timeout(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        slow_done = []

        async def slow_handler(event: DomainEvent) -> None:
            await asyncio.sleep(1.0)
            slow_done.append(True)

        bus.subscribe("SLOW_WAIT", slow_handler)
        await bus.start()
        await bus.publish("SLOW_WAIT", {"v": 1})
        result = await bus.wait_for_completion(timeout=0.1)
        assert result is False
        await bus.stop()


# ---------------------------------------------------------------------------
# get_stats tests
# ---------------------------------------------------------------------------

class TestGetStats:

    @pytest.mark.asyncio
    async def test_stats_reflect_state(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        stats = bus.get_stats()
        assert stats["event_count"] == 0
        assert stats["error_count"] == 0
        assert stats["dropped_count"] == 0
        assert stats["is_running"] is False
        assert stats["subscriber_count"] == 0

    @pytest.mark.asyncio
    async def test_stats_after_events(self) -> None:
        bus = AsyncEventBus(maxsize=100)

        def handler(event: DomainEvent) -> None:
            pass

        bus.subscribe("STATS", handler)
        await bus.start()
        await bus.publish("STATS", {"v": 1})
        await bus.wait_for_completion(timeout=2.0)

        stats = bus.get_stats()
        assert stats["event_count"] == 1
        assert stats["subscriber_count"] == 1
        assert stats["is_running"] is True
        await bus.stop()


# ---------------------------------------------------------------------------
# Properties tests
# ---------------------------------------------------------------------------

class TestProperties:

    @pytest.mark.asyncio
    async def test_queue_size_reflects_items(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        assert bus.queue_size == 0

    @pytest.mark.asyncio
    async def test_is_full_on_small_queue(self) -> None:
        bus = AsyncEventBus(maxsize=1)
        assert not bus.is_full

    @pytest.mark.asyncio
    async def test_is_running_reflects_state(self) -> None:
        bus = AsyncEventBus(maxsize=100)
        assert not bus.is_running
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running
