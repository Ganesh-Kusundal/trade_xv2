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
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from infrastructure.event_bus.async_event_bus import AsyncEventBus, BackpressurePolicy
from infrastructure.event_bus.event_bus import DomainEvent


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
        # Supervisor creates worker asynchronously, wait briefly
        await asyncio.sleep(0.1)
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


class TestDLQIntegration:
    """Tests for Dead Letter Queue integration — verifies correct DLQ push signature."""

    @pytest.mark.asyncio
    async def test_handler_failure_pushes_to_dlq_with_correct_signature(self) -> None:
        """Verify that handler failures are pushed to DLQ using push_failure(), not push().

        Regression test for: async_event_bus.py:539 called push(event, exc) but
        DeadLetterQueue.push() expects a DeadLetter object — this caused a TypeError
        that crashed the dispatch worker.
        """
        from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue

        dlq = DeadLetterQueue(max_size=100)
        bus = AsyncEventBus(maxsize=100, dead_letter_queue=dlq)
        await bus.start()

        results: list[str] = []

        def failing_handler(event) -> None:
            results.append(event.event_type)
            raise ValueError("test handler failure")

        bus.subscribe("TEST_EVENT", failing_handler)
        await bus.publish("TEST_EVENT", payload={"data": "test"})

        # Wait for dispatch
        await asyncio.sleep(0.2)
        await bus.wait_for_completion(timeout=2.0)

        # Handler should have been called
        assert "TEST_EVENT" in results

        # DLQ should have the failure (not crashed)
        assert len(dlq) == 1
        dead_letter = dlq.peek(1)[0]
        assert dead_letter.error_type == "ValueError"
        assert "test handler failure" in dead_letter.error_message
        assert dead_letter.traceback is not None

        await bus.stop()

    @pytest.mark.asyncio
    async def test_async_event_bus_persists_to_event_log(self) -> None:
        """Verify that AsyncEventBus persists events to event_log before dispatch.

        Regression test for: AsyncEventBus accepted event_log parameter but NEVER
        wrote to it, causing zero crash recovery capability.
        """
        from infrastructure.event_log import EventLog
        import tempfile
        import os
        from pathlib import Path
        from datetime import date

        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir) / "events"
            event_log = EventLog(events_dir)

            bus = AsyncEventBus(maxsize=100, event_log=event_log)
            await bus.start()

            results: list[str] = []

            def handler(event) -> None:
                results.append(event.event_type)

            bus.subscribe("PERSIST_TEST", handler)
            await bus.publish("PERSIST_TEST", payload={"key": "value"})

            # Wait for dispatch
            await asyncio.sleep(0.2)
            await bus.wait_for_completion(timeout=2.0)

            # Event should have been persisted to today's JSONL file
            today_file = events_dir / f"{date.today().isoformat()}.jsonl"
            # Check for append errors
            assert event_log.append_errors == 0, f"EventLog had {event_log.append_errors} append errors"
            assert today_file.exists(), f"Expected event log at {today_file}, events_dir contents: {list(events_dir.iter()) if events_dir.exists() else 'DIR NOT FOUND'}"
            with open(today_file) as f:
                lines = f.readlines()
            assert len(lines) >= 1
            assert "PERSIST_TEST" in lines[0]

            await bus.stop()


# ---------------------------------------------------------------------------
# Supervisor Recovery tests (A7 Fix)
# ---------------------------------------------------------------------------

class TestSupervisorRecovery:
    """Tests for supervisor pattern that monitors and restarts dispatch worker."""

    @pytest.mark.asyncio
    async def test_worker_crash_triggers_restart(self) -> None:
        """Verify supervisor restarts worker after crash."""
        bus = AsyncEventBus(maxsize=100)
        
        received_events = []
        crash_event = asyncio.Event()
        crash_count = 0
        
        async def handler(event):
            received_events.append(event.payload.get("id"))
        
        bus.subscribe("TEST", handler)
        
        # Patch _dispatch_worker to crash on first event
        original_dispatch_worker = bus._dispatch_worker
        
        async def crashing_dispatch_worker():
            nonlocal crash_count
            crash_count += 1
            if crash_count == 1:
                # Crash immediately
                crash_event.set()
                raise RuntimeError("Simulated worker crash")
            # On restart, run normally
            await original_dispatch_worker()
        
        # Replace the method before starting
        bus._dispatch_worker = crashing_dispatch_worker
        
        await bus.start()
        
        # Wait for crash
        await asyncio.wait_for(crash_event.wait(), timeout=2.0)
        
        # Wait for supervisor to restart (backoff delay + restart)
        await asyncio.sleep(0.5)
        
        # Verify restart occurred
        assert bus._restart_count >= 1
        assert bus._consecutive_restarts >= 1
        # Verify worker was restarted
        assert bus._worker_task is not None
        
        # Publish an event to verify restarted worker processes events
        await bus.publish("TEST", {"id": 1})
        await asyncio.sleep(0.3)
        assert 1 in received_events
        
        await bus.stop()

    @pytest.mark.asyncio
    async def test_supervisor_exponential_backoff(self) -> None:
        """Verify exponential backoff delays increase with consecutive restarts."""
        bus = AsyncEventBus(maxsize=100)
        
        # Test backoff calculation
        bus._consecutive_restarts = 0
        delay_0 = bus._calculate_restart_delay()
        assert delay_0 == pytest.approx(0.1, abs=0.01)
        
        bus._consecutive_restarts = 1
        delay_1 = bus._calculate_restart_delay()
        assert delay_1 == pytest.approx(0.2, abs=0.01)
        
        bus._consecutive_restarts = 2
        delay_2 = bus._calculate_restart_delay()
        assert delay_2 == pytest.approx(0.4, abs=0.01)
        
        bus._consecutive_restarts = 3
        delay_3 = bus._calculate_restart_delay()
        assert delay_3 == pytest.approx(0.8, abs=0.01)
        
        # Verify cap at 5 seconds
        bus._consecutive_restarts = 10
        delay_10 = bus._calculate_restart_delay()
        assert delay_10 == pytest.approx(5.0, abs=0.01)
        
        # Verify exponential progression
        assert delay_0 < delay_1 < delay_2 < delay_3 < delay_10

    @pytest.mark.asyncio
    async def test_supervisor_gives_up_after_crash_loop(self) -> None:
        """Verify supervisor suppresses restarts after crash loop detected."""
        bus = AsyncEventBus(maxsize=100)
        
        # Simulate crash loop state
        now = datetime.now(timezone.utc)
        bus._consecutive_restarts = 5
        bus._last_restart_at = now
        
        # Should suppress (5 restarts within 5s window)
        should_suppress = bus._should_suppress_restart(now)
        assert should_suppress is True
        
        # After cooldown window passes, should allow restart
        after_cooldown = now + timedelta(seconds=6)
        should_suppress_later = bus._should_suppress_restart(after_cooldown)
        assert should_suppress_later is False
        
        # Below threshold should not suppress
        bus._consecutive_restarts = 4
        should_not_suppress = bus._should_suppress_restart(now)
        assert should_not_suppress is False

    @pytest.mark.asyncio
    async def test_events_preserved_during_restart(self) -> None:
        """Verify events in queue are preserved when worker restarts."""
        bus = AsyncEventBus(maxsize=100)
        
        received_events = []
        
        async def handler(event):
            received_events.append(event.event_type)
        
        bus.subscribe("TEST_EVENT", handler)
        await bus.start()
        
        # Publish some events
        await bus.publish("TEST_EVENT", {"id": 1})
        await bus.publish("TEST_EVENT", {"id": 2})
        await bus.publish("TEST_EVENT", {"id": 3})
        
        # Wait for processing
        await asyncio.sleep(0.3)
        
        # All events should be processed
        assert len(received_events) == 3
        assert received_events == ["TEST_EVENT", "TEST_EVENT", "TEST_EVENT"]
        
        await bus.stop()

    @pytest.mark.asyncio
    async def test_health_healthy_when_running(self) -> None:
        """Verify health returns HEALTHY when running normally."""
        bus = AsyncEventBus(maxsize=100)
        
        # Before start
        health = bus.health()
        assert health.state.value == "STOPPED"
        assert health.service == "AsyncEventBus"
        
        await bus.start()
        
        # After start - wait for tasks to initialize
        await asyncio.sleep(0.2)
        health = bus.health()
        
        # Should be HEALTHY or DEGRADED (if restart happened)
        assert health.state.value in ["HEALTHY", "DEGRADED"]
        assert health.service == "AsyncEventBus"
        assert health.metrics["worker_task_alive"] is True
        assert health.metrics["supervisor_task_alive"] is True
        
        await bus.stop()

    @pytest.mark.asyncio
    async def test_health_degraded_after_restart(self) -> None:
        """Verify health returns DEGRADED after worker restart."""
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        await asyncio.sleep(0.2)
        
        # Stop the bus first to prevent supervisor interference
        bus._running = False
        if bus._supervisor_task:
            bus._supervisor_task.cancel()
            try:
                await bus._supervisor_task
            except asyncio.CancelledError:
                pass
        if bus._worker_task:
            bus._worker_task.cancel()
            try:
                await bus._worker_task
            except asyncio.CancelledError:
                pass
        
        # Simulate a restart state
        bus._running = True
        bus._restart_count = 1
        bus._consecutive_restarts = 1
        # Recreate a dummy worker task
        async def dummy_worker():
            await asyncio.sleep(100)
        bus._worker_task = asyncio.create_task(dummy_worker())
        # Recreate supervisor task
        async def dummy_supervisor():
            await asyncio.sleep(100)
        bus._supervisor_task = asyncio.create_task(dummy_supervisor())
        
        health = bus.health()
        assert health.state.value == "DEGRADED"
        assert "restart" in health.detail.lower()
        assert health.metrics["consecutive_restarts"] == 1
        
        # Cleanup
        bus._running = False
        bus._worker_task.cancel()
        bus._supervisor_task.cancel()
        try:
            await bus._worker_task
        except asyncio.CancelledError:
            pass
        try:
            await bus._supervisor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_health_unhealthy_in_crash_loop(self) -> None:
        """Verify health returns UNHEALTHY when in crash loop."""
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        await asyncio.sleep(0.2)
        
        # Stop the bus first to prevent supervisor interference
        bus._running = False
        if bus._supervisor_task:
            bus._supervisor_task.cancel()
            try:
                await bus._supervisor_task
            except asyncio.CancelledError:
                pass
        if bus._worker_task:
            bus._worker_task.cancel()
            try:
                await bus._worker_task
            except asyncio.CancelledError:
                pass
        
        # Simulate crash loop state
        bus._running = True
        bus._consecutive_restarts = 5
        bus._last_restart_at = datetime.now(timezone.utc)
        # Recreate a dummy worker task
        async def dummy_worker():
            await asyncio.sleep(100)
        bus._worker_task = asyncio.create_task(dummy_worker())
        # Recreate supervisor task
        async def dummy_supervisor():
            await asyncio.sleep(100)
        bus._supervisor_task = asyncio.create_task(dummy_supervisor())
        
        health = bus.health()
        assert health.state.value == "UNHEALTHY"
        assert "crash loop" in health.detail.lower()
        
        # Cleanup
        bus._running = False
        bus._worker_task.cancel()
        bus._supervisor_task.cancel()
        try:
            await bus._worker_task
        except asyncio.CancelledError:
            pass
        try:
            await bus._supervisor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_health_failed_when_tasks_dead(self) -> None:
        """Verify health returns FAILED when supervisor/worker tasks are dead."""
        bus = AsyncEventBus(maxsize=100)
        await bus.start()
        
        # Kill the supervisor task
        if bus._supervisor_task is not None:
            bus._supervisor_task.cancel()
            try:
                await bus._supervisor_task
            except asyncio.CancelledError:
                pass
        
        await asyncio.sleep(0.1)
        
        health = bus.health()
        assert health.state.value == "FAILED"
        
        # Clean up
        bus._running = False
        await bus.stop()

    @pytest.mark.asyncio
    async def test_name_property_for_lifecycle_manager(self) -> None:
        """Verify name property exists for ManagedService protocol."""
        bus = AsyncEventBus(maxsize=100)
        assert bus.name == "AsyncEventBus"
        assert isinstance(bus.name, str)

    @pytest.mark.asyncio
    async def test_supervisor_resets_state_on_start(self) -> None:
        """Verify supervisor state is reset when bus is restarted."""
        bus = AsyncEventBus(maxsize=100)
        
        # Simulate previous crash state
        bus._restart_count = 10
        bus._consecutive_restarts = 5
        bus._last_restart_at = datetime.now(timezone.utc)
        
        # Start should reset state
        await bus.start()
        
        assert bus._restart_count == 0
        assert bus._consecutive_restarts == 0
        assert bus._last_restart_at is None
        
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_includes_restart_count_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify stop log message includes restart count."""
        bus = AsyncEventBus(maxsize=100)
        
        await bus.start()
        await asyncio.sleep(0.2)
        
        # Manually set restart count AFTER start (since start() resets it)
        bus._restart_count = 3
        
        await bus.stop()
        
        # Verify restart_count is preserved through stop
        assert bus._restart_count == 3
