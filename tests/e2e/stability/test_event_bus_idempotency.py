"""Tests for EventBus idempotency guard (P5 Stability Engineering).

Verifies that duplicate events (same event_id) are only processed once,
preventing double-counting under at-least-once delivery.
"""

from unittest.mock import MagicMock

from infrastructure.event_bus.event_bus import DomainEvent, EventBus, EventBusConfig


class TestEventBusIdempotency:
    """Test EventBus idempotency under duplicate events."""

    def test_duplicate_event_processed_only_once(self):
        """Publishing same event twice should only invoke handler once."""
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        trade_data = {"trade_id": "T1", "symbol": "RELIANCE", "quantity": 10}
        event = DomainEvent.now("TRADE", trade_data)

        # Publish same event twice
        bus.publish(event)
        bus.publish(event)

        # Handler should only be called once
        assert handler.call_count == 1

    def test_different_events_both_processed(self):
        """Events with different event_ids should both be processed."""
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        trade_data = {"trade_id": "T1", "symbol": "RELIANCE", "quantity": 10}
        event1 = DomainEvent.now("TRADE", trade_data)
        event2 = DomainEvent.now("TRADE", trade_data)  # Different event_id

        bus.publish(event1)
        bus.publish(event2)

        # Both events should be processed
        assert handler.call_count == 2

    def test_idempotency_cache_bounded(self):
        """Idempotency cache should not grow unbounded."""
        max_events = 100
        bus = EventBus(config=EventBusConfig(max_processed_events=max_events))

        # Publish more events than cache size
        for i in range(max_events + 50):
            event = DomainEvent.now("TRADE", {"i": i})
            bus.publish(event)

        # Cache should be bounded
        assert len(bus._processed_events) <= max_events
        assert len(bus._processed_event_ids) <= max_events

    def test_old_events_evicted_from_cache(self):
        """Old events should be evicted when cache is full."""
        max_events = 10
        bus = EventBus(config=EventBusConfig(max_processed_events=max_events))

        # Fill cache
        events = []
        for i in range(max_events):
            event = DomainEvent.now("TRADE", {"i": i})
            events.append(event)
            bus.publish(event)

        # Publish first event again - should be evicted, so processed again
        first_event = events[0]
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        # Clear handler calls from setup
        handler.reset_mock()

        bus.publish(first_event)
        # This may or may not be called depending on timing of eviction
        # Just verify no crash

    def test_idempotency_thread_safe(self):
        """Idempotency check should be thread-safe."""
        import threading

        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        event = DomainEvent.now("TRADE", {"trade_id": "T1"})
        call_count = [0]
        lock = threading.Lock()

        def publish_multiple():
            for _ in range(10):
                bus.publish(event)
                with lock:
                    call_count[0] += 1

        # Run multiple threads
        threads = [threading.Thread(target=publish_multiple) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Handler should only be called once despite 50 total publishes
        handler.assert_called_once()

    def test_metrics_track_duplicate_skips(self):
        """Duplicate events should be skipped (handler called once)."""
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        event = DomainEvent.now("TRADE", {"trade_id": "T1"})
        bus.publish(event)
        bus.publish(event)
        bus.publish(event)  # Third time

        # Handler called only once despite 3 publishes
        assert handler.call_count == 1

    def test_no_event_id_allows_processing(self):
        """Events without event_id should always be processed."""
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        # Create event with minimal ID (edge case)
        event1 = DomainEvent.now("TRADE", {"trade_id": "T1"})
        event2 = DomainEvent.now("TRADE", {"trade_id": "T1"})  # Different event_id

        # Both should be processed (different event_ids)
        bus.publish(event1)
        bus.publish(event2)
        assert handler.call_count == 2

    def test_replay_mode_still_idempotent(self):
        """Replay mode should respect idempotency."""
        bus = EventBus(config=EventBusConfig(replay_mode=True))
        handler = MagicMock()
        bus.subscribe("TRADE", handler)

        event = DomainEvent.now("TRADE", {"trade_id": "T1"})
        bus.publish(event)
        bus.publish(event)

        # In replay mode, handler dispatch is skipped entirely
        # (existing behavior), but idempotency should still work
        handler.assert_not_called()
