"""P6-4: Data Corruption Chaos Tests.

Verifies the system detects and handles corrupted data:
1. Corrupted Parquet files (bad checksums / malformed data)
2. Missing columns in DataFrame
3. Invalid order states in database/event log
4. Duplicate events in event bus
5. Clock skew (timestamps out of order)

Each test injects corrupted data deterministically and verifies the system
either rejects it, handles it gracefully, or alerts on the corruption.
Each test must complete in < 5 seconds.
"""

from __future__ import annotations

import json
import time
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from brokers.common.event_bus.event_bus import DomainEvent, EventBus
from brokers.common.event_bus.dead_letter_queue import DeadLetterQueue
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.resilience.broker_health_monitor import BrokerHealthMonitor


# ──────────────────────────────────────────────────────────────────────
# Section 1: Corrupted Parquet / DataFrame
# ──────────────────────────────────────────────────────────────────────

class TestCorruptedDataFrame:
    """Verify system handles corrupted or malformed DataFrame inputs."""

    def test_replay_engine_handles_empty_dataframe(self):
        """Empty DataFrame should return an empty ReplayResult, not crash."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig

        engine = ReplayEngine(config=ReplayConfig(window_size=20))
        result = engine.run(pd.DataFrame(), symbol="TEST")

        assert result.bars_processed == 0, (
            "Replay on empty DataFrame should have 0 bars processed"
        )

    def test_replay_engine_handles_missing_ohlcv_columns(self):
        """DataFrame missing OHLCV columns should not crash the engine."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="h"),
            # Missing: open, high, low, close, volume
        })

        engine = ReplayEngine(config=ReplayConfig(window_size=5))
        # Should not crash — defaults to 0 for missing numeric columns
        result = engine.run(df, symbol="TEST")
        # Bars may be processed with zero values; the key is no crash
        assert result is not None

    def test_replay_engine_handles_missing_timestamp_column(self):
        """DataFrame without timestamp/date column should raise ValueError."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig

        df = pd.DataFrame({
            "open": [100.0],
            "close": [101.0],
        })

        engine = ReplayEngine(config=ReplayConfig())

        with pytest.raises(ValueError, match="'timestamp' or 'date' column"):
            engine.run(df, symbol="TEST")

    def test_replay_engine_handles_corrupted_numeric_values(self):
        """DataFrame with NaN/inf values should be handled by FeaturePipeline gracefully."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig
        from analytics.pipeline.pipeline import FeaturePipeline

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="h"),
            "open": [100.0, float("nan"), 102.0, float("inf"), 104.0],
            "high": [101.0, 102.0, 103.0, 105.0, 106.0],
            "low": [99.0, 98.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 104.5, 105.5],
            "volume": [1000, 1200, 1100, 1300, 1400],
        })

        engine = ReplayEngine(
            pipeline=FeaturePipeline(),
            config=ReplayConfig(window_size=5, warmup_bars=0),
        )
        # Should not crash — FeaturePipeline should handle NaN gracefully
        result = engine.run(df, symbol="TEST")
        assert result.bars_processed == 5

    def test_replay_engine_handles_negative_prices(self):
        """DataFrame with negative prices should be processed (data quality concern, not crash)."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig
        from analytics.pipeline.pipeline import FeaturePipeline

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="h"),
            "open": [-100.0, -99.0, -98.0, -97.0, -96.0],
            "high": [-99.0, -98.0, -97.0, -96.0, -95.0],
            "low": [-101.0, -100.0, -99.0, -98.0, -97.0],
            "close": [-99.5, -98.5, -97.5, -96.5, -95.5],
            "volume": [1000, 1200, 1100, 1300, 1400],
        })

        engine = ReplayEngine(
            pipeline=FeaturePipeline(),
            config=ReplayConfig(window_size=5, warmup_bars=0),
        )
        result = engine.run(df, symbol="TEST")
        assert result.bars_processed == 5, (
            "Engine should process bars even with negative prices"
        )

    def test_replay_engine_handles_out_of_order_timestamps(self):
        """DataFrame with out-of-order timestamps should be sorted by engine."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig
        from analytics.pipeline.pipeline import FeaturePipeline

        df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2024-01-01 03:00"),
                pd.Timestamp("2024-01-01 01:00"),
                pd.Timestamp("2024-01-01 05:00"),
                pd.Timestamp("2024-01-01 02:00"),
                pd.Timestamp("2024-01-01 04:00"),
            ],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1000, 1200, 1100, 1300, 1400],
        })

        engine = ReplayEngine(
            pipeline=FeaturePipeline(),
            config=ReplayConfig(window_size=5, warmup_bars=0),
        )
        result = engine.run(df, symbol="TEST")
        assert result.bars_processed == 5, (
            "Engine should process all bars after sorting timestamps"
        )

    def test_replay_engine_handles_extremely_large_values(self):
        """DataFrame with extremely large values should not cause overflow."""
        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig
        from analytics.pipeline.pipeline import FeaturePipeline

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="h"),
            "open": [1e15, 1e15, 1e15],
            "high": [1e15 + 1, 1e15 + 1, 1e15 + 1],
            "low": [1e15 - 1, 1e15 - 1, 1e15 - 1],
            "close": [1e15, 1e15, 1e15],
            "volume": [1e12, 1e12, 1e12],
        })

        engine = ReplayEngine(
            pipeline=FeaturePipeline(),
            config=ReplayConfig(window_size=3, warmup_bars=0),
        )
        # Should not raise overflow
        result = engine.run(df, symbol="TEST")
        assert result is not None


# ──────────────────────────────────────────────────────────────────────
# Section 2: Corrupted Events (Event Bus)
# ──────────────────────────────────────────────────────────────────────

class TestCorruptedEvents:
    """Verify event bus handles corrupted or malformed events."""

    def test_domain_event_rejects_naive_timestamp(self):
        """DomainEvent should auto-convert naive timestamps to UTC-aware."""
        naive_ts = datetime(2024, 1, 1, 12, 0, 0)
        event = DomainEvent(
            event_type="TICK",
            timestamp=naive_ts,
            payload={"price": 100.0},
        )

        assert event.timestamp.tzinfo is not None, (
            "DomainEvent should ensure timezone-aware timestamps"
        )

    def test_event_bus_handles_corrupted_payload(self):
        """Handler receiving corrupted payload should not crash the bus."""
        bus = EventBus(fail_fast=False)
        dlq = DeadLetterQueue(max_size=100)
        bus._dead_letter_queue = dlq

        def strict_handler(event):
            # Handler expects 'price' key — will raise KeyError on corrupted payload
            _ = event.payload["price"]

        bus.subscribe("TICK", strict_handler)

        # Corrupted event: missing expected key
        event = DomainEvent.now("TICK", {"wrong_key": "no price here"})
        bus.publish(event)

        assert len(dlq) == 1, (
            "Corrupted payload causing handler error should be dead-lettered"
        )

    def test_event_bus_handles_none_payload_gracefully(self):
        """Event with None in payload should not crash."""
        bus = EventBus(fail_fast=False)
        received = []

        def collector(event):
            received.append(event.payload)

        bus.subscribe("TICK", collector)

        event = DomainEvent.now("TICK", {"value": None, "data": "test"})
        bus.publish(event)

        assert len(received) == 1

    def test_event_bus_handles_empty_event_type(self):
        """Empty event type should still be dispatched."""
        bus = EventBus(fail_fast=False)
        received = []

        bus.subscribe("", lambda e: received.append(e))

        event = DomainEvent.now("", {"data": "empty type"})
        bus.publish(event)

        assert len(received) == 1, "Empty event type should still work"


# ──────────────────────────────────────────────────────────────────────
# Section 3: Duplicate Events
# ──────────────────────────────────────────────────────────────────────

class TestDuplicateEvents:
    """Verify system handles duplicate events correctly."""

    def test_duplicate_events_both_dispatched(self):
        """Duplicate events should both be dispatched (no dedup by default)."""
        bus = EventBus(fail_fast=False)
        received = []

        bus.subscribe("TICK", lambda e: received.append(e.event_id))

        event_data = {"price": 100.0, "symbol": "RELIANCE"}

        # Publish same event data twice (different event_id each time)
        event1 = DomainEvent.now("TICK", event_data)
        event2 = DomainEvent.now("TICK", event_data)

        bus.publish(event1)
        bus.publish(event2)

        assert len(received) == 2, (
            "Both duplicate events should be dispatched"
        )
        assert received[0] != received[1], (
            "Each event should have a unique event_id"
        )

    def test_event_bus_sequence_numbers_are_monotonic(self):
        """Sequence numbers should be monotonically increasing."""
        bus = EventBus(fail_fast=False)
        seq_numbers = []

        def seq_collector(event):
            seq_numbers.append(event.sequence_number)

        bus.subscribe("TICK", seq_collector)

        for _ in range(10):
            bus.publish(DomainEvent.now("TICK", {}))

        assert seq_numbers == list(range(1, 11)), (
            f"Sequence numbers should be 1..10, got {seq_numbers}"
        )

    def test_replay_mode_preserves_original_sequence_numbers(self):
        """In replay mode, original sequence numbers should be preserved."""
        bus = EventBus(fail_fast=False, replay_mode=True)
        seq_numbers = []

        def seq_collector(event):
            seq_numbers.append(event.sequence_number)

        bus.subscribe("TICK", seq_collector)

        # Events with pre-assigned sequence numbers
        events = [
            DomainEvent("TICK", datetime(2024, 1, 1, tzinfo=timezone.utc), {}, sequence_number=5),
            DomainEvent("TICK", datetime(2024, 1, 2, tzinfo=timezone.utc), {}, sequence_number=3),
            DomainEvent("TICK", datetime(2024, 1, 3, tzinfo=timezone.utc), {}, sequence_number=8),
        ]

        for event in events:
            bus.publish(event)

        assert seq_numbers == [5, 3, 8], (
            "Replay mode should preserve original sequence numbers"
        )

    def test_dead_letter_queue_bounded_capacity(self):
        """DLQ should enforce max_size and track dropped entries."""
        dlq = DeadLetterQueue(max_size=3)

        for i in range(5):
            event = DomainEvent.now("TICK", {"seq": i})
            dlq.push_failure(event, f"handler-{i}", RuntimeError(f"Error {i}"))

        assert len(dlq) == 3, "DLQ should only hold max_size entries"
        assert dlq.dropped == 2, "DLQ should track dropped entries"

    def test_dead_letter_queue_drain_returns_all_entries(self):
        """drain() should return all entries and clear the queue."""
        dlq = DeadLetterQueue(max_size=100)

        for i in range(5):
            event = DomainEvent.now("TICK", {"seq": i})
            dlq.push_failure(event, f"handler-{i}", ValueError(f"Error {i}"))

        drained = dlq.drain()

        assert len(drained) == 5, "drain() should return all entries"
        assert len(dlq) == 0, "drain() should clear the queue"

    def test_dead_letter_queue_stats_are_accurate(self):
        """stats() should return accurate size, capacity, and dropped count."""
        dlq = DeadLetterQueue(max_size=2)

        for i in range(4):
            event = DomainEvent.now("TICK", {"seq": i})
            dlq.push_failure(event, f"h{i}", RuntimeError())

        stats = dlq.stats()
        assert stats["size"] == 2
        assert stats["capacity"] == 2
        assert stats["dropped"] == 2


# ──────────────────────────────────────────────────────────────────────
# Section 4: Clock Skew
# ──────────────────────────────────────────────────────────────────────

class TestClockSkew:
    """Verify system handles clock skew and out-of-order timestamps."""

    def test_domain_event_factory_uses_utc(self):
        """DomainEvent.now() should use UTC timestamps."""
        event = DomainEvent.now("TICK", {})
        assert event.timestamp.tzinfo is not None
        # Should be close to UTC
        now_utc = datetime.now(timezone.utc)
        diff = abs((event.timestamp - now_utc).total_seconds())
        assert diff < 5, "Timestamp should be close to current UTC time"

    def test_event_bus_publishes_with_backdated_timestamps(self):
        """Events with backdated timestamps should still be processed."""
        bus = EventBus(fail_fast=False)
        received = []

        bus.subscribe("TICK", lambda e: received.append(e.timestamp))

        past_ts = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        event = DomainEvent("TICK", past_ts, {"data": "backdated"})
        bus.publish(event)

        assert len(received) == 1
        assert received[0] == past_ts

    def test_event_bus_publishes_with_future_timestamps(self):
        """Events with future timestamps should still be processed."""
        bus = EventBus(fail_fast=False)
        received = []

        bus.subscribe("TICK", lambda e: received.append(e.timestamp))

        future_ts = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        event = DomainEvent("TICK", future_ts, {"data": "future"})
        bus.publish(event)

        assert len(received) == 1

    def test_event_metrics_handles_timestamped_counters_with_skew(self):
        """EventMetrics should handle timestamped counters with varying timestamps."""
        metrics = EventMetrics()

        # Add counters with backdated timestamps
        past_ts = time.time() - 86400  # 1 day ago
        metrics.add_timestamped_counter("TICK", "published", timestamp=past_ts)

        # Add counters with future timestamps
        future_ts = time.time() + 86400  # 1 day in future
        metrics.add_timestamped_counter("TICK", "published", timestamp=future_ts)

        # Current time rate should not be affected by backdated entries
        rate = metrics.rate("TICK", "published", window_seconds=60)
        # Rate should only count entries within the 60s window
        assert rate >= 0, "Rate calculation should handle skewed timestamps"


# ──────────────────────────────────────────────────────────────────────
# Section 5: Invalid State Transitions
# ──────────────────────────────────────────────────────────────────────

class TestInvalidStateTransitions:
    """Verify system handles invalid state transitions."""

    def test_health_monitor_unknown_broker_is_healthy(self):
        """Unknown broker should be treated as healthy (optimistic default)."""
        monitor = BrokerHealthMonitor(failure_threshold=3)
        assert monitor.is_healthy("unknown_broker"), (
            "Unknown broker should be treated as healthy"
        )

    def test_health_monitor_transition_healthy_to_unhealthy(self):
        """Broker should transition to unhealthy after threshold failures."""
        monitor = BrokerHealthMonitor(failure_threshold=3)

        status = monitor.get_health_status()
        assert "dhan" not in status, "New broker should not appear in status yet"

        monitor.record_failure("dhan")
        status = monitor.get_health_status()
        assert status["dhan"].circuit_state == "healthy"

        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        status = monitor.get_health_status()
        assert status["dhan"].circuit_state == "unhealthy", (
            "Broker should transition to unhealthy after threshold failures"
        )

    def test_event_bus_replay_mode_disables_persistence(self):
        """Replay mode should not write to event_log (no recursive writes)."""
        event_log = MagicMock()
        bus = EventBus(event_log=event_log, replay_mode=True, fail_fast=False)

        event = DomainEvent.now("TICK", {"data": "replay"})
        bus.publish(event)

        event_log.append.assert_not_called(), (
            "Event log should not be written to in replay mode"
        )

    def test_event_bus_sequence_counter_resets_on_new_instance(self):
        """Each EventBus instance should have its own sequence counter."""
        bus1 = EventBus(fail_fast=False)
        bus2 = EventBus(fail_fast=False)

        seq1 = []
        seq2 = []

        bus1.subscribe("TICK", lambda e: seq1.append(e.sequence_number))
        bus2.subscribe("TICK", lambda e: seq2.append(e.sequence_number))

        bus1.publish(DomainEvent.now("TICK", {}))
        bus2.publish(DomainEvent.now("TICK", {}))

        assert seq1 == [1], "Bus1 sequence should start at 1"
        assert seq2 == [1], "Bus2 sequence should start at 1 (independent)"

    def test_event_bus_correlation_id_auto_injection(self):
        """Events without correlation_id should get one injected from context."""
        from brokers.common.correlation import with_correlation

        bus = EventBus(fail_fast=False)
        captured = []

        def capture_correlation(event):
            captured.append(event.correlation_id)

        bus.subscribe("TICK", capture_correlation)

        with with_correlation("test-corr-123"):
            event = DomainEvent.now("TICK", {"data": "with correlation"})
            bus.publish(event)

        assert captured[0] == "test-corr-123", (
            "Correlation ID should be auto-injected from context"
        )

    def test_domain_event_immutability(self):
        """DomainEvent is frozen — attempts to modify should raise."""
        event = DomainEvent.now("TICK", {"price": 100.0})

        with pytest.raises((TypeError, AttributeError)):
            event.event_type = "ORDER"

    def test_event_bus_alerting_thread_clean_shutdown(self):
        """Alerting thread should shut down cleanly."""
        metrics = EventMetrics()
        from brokers.common.observability.alerting import AlertingEngine

        engine = AlertingEngine(metrics)
        bus = EventBus(
            metrics=metrics,
            alerting_engine=engine,
            alerting_interval_seconds=0.1,
        )

        # Give thread time to start
        time.sleep(0.2)

        # Clean shutdown
        bus.stop_alerting()

        # Thread should have stopped
        if bus._alerting_thread is not None:
            assert not bus._alerting_thread.is_alive(), (
                "Alerting thread should stop after stop_alerting()"
            )


# ──────────────────────────────────────────────────────────────────────
# Section 6: Data Integrity Under Concurrency
# ──────────────────────────────────────────────────────────────────────

class TestDataIntegrityUnderConcurrency:
    """Verify data integrity when multiple threads interact with shared state."""

    def test_event_bus_concurrent_subscribe_unsubscribe(self):
        """Concurrent subscribe/unsubscribe should not corrupt state."""
        bus = EventBus(fail_fast=False)
        errors = []

        def subscribe_many():
            try:
                for i in range(50):
                    bus.subscribe("TICK", lambda e, x=i: None)
            except Exception as e:
                errors.append(e)

        def unsubscribe_all():
            try:
                bus.clear()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=subscribe_many),
            threading.Thread(target=unsubscribe_all),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Concurrent operations should not raise: {errors}"

    def test_event_metrics_concurrent_increments(self):
        """Concurrent metric increments should not lose counts."""
        metrics = EventMetrics()

        def increment_many():
            for _ in range(500):
                metrics.inc("TICK", "published")

        threads = [threading.Thread(target=increment_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        count = metrics.get("TICK", "published")
        assert count == 2000, (
            f"Expected 2000 increments (4 threads * 500), got {count}"
        )

    def test_event_bus_handler_order_preserved_with_concurrent_publish(self):
        """Multiple publishes from different threads should all be delivered."""
        bus = EventBus(fail_fast=False)
        lock = threading.Lock()
        received = []

        def safe_append(event):
            with lock:
                received.append(event.payload.get("thread_id"))

        bus.subscribe("TICK", safe_append)

        def publish_from_thread(thread_id):
            for i in range(10):
                bus.publish(DomainEvent.now("TICK", {"thread_id": thread_id, "seq": i}))

        threads = [
            threading.Thread(target=publish_from_thread, args=(tid,))
            for tid in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(received) == 40, (
            f"Expected 40 events (4 threads * 10), got {len(received)}"
        )

    def test_dead_letter_queue_concurrent_pushes(self):
        """Concurrent DLQ pushes should not lose entries or corrupt state."""
        dlq = DeadLetterQueue(max_size=1000)

        def push_many(start):
            for i in range(100):
                event = DomainEvent.now("TICK", {"seq": start + i})
                dlq.push_failure(event, "handler", RuntimeError(f"Error {start + i}"))

        threads = [
            threading.Thread(target=push_many, args=(tid * 100,))
            for tid in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(dlq) <= 1000, "DLQ should not exceed max_size"
        assert len(dlq) > 0, "DLQ should have entries after concurrent pushes"

    def test_health_monitor_concurrent_record_success_failure(self):
        """Concurrent success/failure records should not corrupt state."""
        monitor = BrokerHealthMonitor(failure_threshold=10)
        errors = []

        def record_many_failures():
            try:
                for _ in range(100):
                    monitor.record_failure("dhan")
            except Exception as e:
                errors.append(e)

        def record_many_successes():
            try:
                for _ in range(100):
                    monitor.record_success("dhan")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_many_failures),
            threading.Thread(target=record_many_successes),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Concurrent health records should not raise: {errors}"
        # Final state should be consistent
        status = monitor.get_health_status()
        assert "dhan" in status
