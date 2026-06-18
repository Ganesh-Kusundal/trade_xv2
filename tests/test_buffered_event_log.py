"""Tests for BufferedEventLog (Phase 3).

Covers:
- Buffered append (no immediate fsync)
- Flush on threshold (buffer size >= flush_threshold)
- Flush on interval (time-based auto-flush)
- sync_mode (immediate flush for critical events)
- Explicit flush()
- close() flushes remaining buffer
- get_stats
- Buffer persistence after failed flush
- Thread safety of buffered writes
- Inherited replay() from EventLog
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from brokers.common.event_bus.event_bus import DomainEvent
from brokers.common.event_log import BufferedEventLog, EventLog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_events_dir(tmp_path: Path) -> Path:
    return tmp_path / "events"


@pytest.fixture
def sample_event() -> DomainEvent:
    return DomainEvent(
        event_type="ORDER_PLACED",
        timestamp=datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc),
        payload={"order_id": "O1", "symbol": "RELIANCE"},
        symbol="RELIANCE",
        source="test",
        sequence_number=1,
    )


@pytest.fixture
def buffered_log(tmp_events_dir: Path) -> BufferedEventLog:
    return BufferedEventLog(
        events_dir=tmp_events_dir,
        flush_threshold=5,
        flush_interval=10.0,  # Long interval to avoid time-based flushes
    )


# ---------------------------------------------------------------------------
# Basic append tests
# ---------------------------------------------------------------------------

class TestBufferedAppend:

    def test_append_adds_to_buffer(self, buffered_log: BufferedEventLog, sample_event: DomainEvent) -> None:
        """Events should be buffered, not immediately written."""
        buffered_log.append(sample_event)
        stats = buffered_log.get_stats()
        assert stats["buffer_size"] == 1

    def test_append_multiple_events_fill_buffer(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """After reaching threshold, buffer should flush."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=3,
            flush_interval=10.0,
        )
        # Append 3 events (reaching threshold)
        for i in range(3):
            evt = DomainEvent(
                event_type="TEST",
                timestamp=datetime(2026, 1, 15, 9, 15, i, tzinfo=timezone.utc),
                payload={"n": i},
                sequence_number=i,
            )
            log.append(evt)

        # Buffer should have been flushed
        stats = log.get_stats()
        assert stats["buffer_size"] == 0
        assert stats["flush_count"] >= 1


# ---------------------------------------------------------------------------
# Flush tests
# ---------------------------------------------------------------------------

class TestFlush:

    def test_explicit_flush_writes_buffer(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """flush() should write all buffered events to disk."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,  # High threshold to avoid auto-flush
            flush_interval=10.0,
        )
        log.append(sample_event)
        log.append(sample_event)
        assert log.get_stats()["buffer_size"] == 2

        log.flush()
        assert log.get_stats()["buffer_size"] == 0
        assert log.get_stats()["flush_count"] == 1

    def test_flush_empty_buffer_is_noop(self, buffered_log: BufferedEventLog) -> None:
        """flush() on empty buffer should not increment flush count."""
        initial_count = buffered_log._flush_count
        buffered_log.flush()
        assert buffered_log._flush_count == initial_count

    def test_sync_mode_flushes_immediately(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """sync_mode=True should flush immediately regardless of threshold."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        log.append(sample_event, sync_mode=True)
        assert log.get_stats()["buffer_size"] == 0
        assert log.get_stats()["flush_count"] == 1


# ---------------------------------------------------------------------------
# Time-based auto-flush tests
# ---------------------------------------------------------------------------

class TestTimeIntervalFlush:

    def test_append_triggers_time_based_flush(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """After flush_interval has elapsed, next append should trigger flush."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=0.1,  # 100ms
        )
        log.append(sample_event)

        # Wait for interval to elapse
        time.sleep(0.15)

        # Next append should trigger flush
        evt2 = DomainEvent(
            event_type="TEST",
            timestamp=datetime(2026, 1, 15, 9, 16, 0, tzinfo=timezone.utc),
            payload={"n": 2},
            sequence_number=2,
        )
        log.append(evt2)

        assert log.get_stats()["buffer_size"] == 0
        assert log.get_stats()["flush_count"] == 1


# ---------------------------------------------------------------------------
# Close tests
# ---------------------------------------------------------------------------

class TestClose:

    def test_close_flushes_remaining_buffer(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """close() should flush remaining buffered events."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        log.append(sample_event)
        assert log.get_stats()["buffer_size"] == 1

        log.close()
        # After close, the buffer should be flushed and handle closed
        assert log.get_stats()["buffer_size"] == 0

    def test_context_manager_closes_log(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        with BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        ) as log:
            log.append(sample_event)

        # Buffer should have been flushed on exit
        assert log.get_stats()["buffer_size"] == 0


# ---------------------------------------------------------------------------
# Disk persistence tests
# ---------------------------------------------------------------------------

class TestDiskPersistence:

    def test_flushed_events_are_readable(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """Events should be readable from disk after flush."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        log.append(sample_event)
        log.flush()
        log.close()

        # Read back using parent class replay
        replayed = log.replay()
        assert len(replayed) == 1
        assert replayed[0].event_type == "ORDER_PLACED"
        assert replayed[0].payload["order_id"] == "O1"

    def test_multiple_events_round_trip(
        self, tmp_events_dir: Path
    ) -> None:
        """Multiple events should round-trip correctly."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=3,
            flush_interval=10.0,
        )
        events = []
        for i in range(5):
            evt = DomainEvent(
                event_type="TRADE",
                timestamp=datetime(2026, 1, 15, 9, 15, i, tzinfo=timezone.utc),
                payload={"trade_id": f"T{i}", "price": 100.0 + i},
                symbol="RELIANCE",
                sequence_number=i,
            )
            events.append(evt)
            log.append(evt)

        log.close()
        replayed = log.replay()
        assert len(replayed) == 5


# ---------------------------------------------------------------------------
# get_stats tests
# ---------------------------------------------------------------------------

class TestGetStats:

    def test_initial_stats(self, buffered_log: BufferedEventLog) -> None:
        stats = buffered_log.get_stats()
        assert stats["buffer_size"] == 0
        assert stats["flush_count"] == 0
        assert stats["flush_threshold"] == 5
        assert stats["flush_interval"] == 10.0

    def test_stats_after_appends(self, buffered_log: BufferedEventLog, sample_event: DomainEvent) -> None:
        buffered_log.append(sample_event)
        stats = buffered_log.get_stats()
        assert stats["buffer_size"] == 1

    def test_stats_after_flush(self, buffered_log: BufferedEventLog, sample_event: DomainEvent) -> None:
        buffered_log.append(sample_event)
        buffered_log.flush()
        stats = buffered_log.get_stats()
        assert stats["buffer_size"] == 0
        assert stats["flush_count"] == 1


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------

class TestThreadSafety:

    def test_concurrent_appends(
        self, tmp_events_dir: Path
    ) -> None:
        """Multiple threads appending should not corrupt the buffer."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        errors = []

        def append_events(start: int, count: int) -> None:
            try:
                for i in range(count):
                    evt = DomainEvent(
                        event_type="CONCURRENT",
                        timestamp=datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc),
                        payload={"thread": start, "n": i},
                        sequence_number=start * 100 + i,
                    )
                    log.append(evt)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=append_events, args=(i, 10))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        log.close()

        # Verify all events were written
        replayed = log.replay()
        assert len(replayed) == 50


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_failed_flush_preserves_buffer(
        self, tmp_events_dir: Path, sample_event: DomainEvent,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If flush fails, buffer should not be cleared (retry next time)."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        log.append(sample_event)

        # Simulate write failure
        with patch.object(log, "_ensure_handle", side_effect=OSError("disk full")):
            log.flush()

        # Buffer should still have the event
        assert log.get_stats()["buffer_size"] == 1

    def test_failed_flush_logs_error(
        self, tmp_events_dir: Path, sample_event: DomainEvent,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Failed flush should log an error."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        log.append(sample_event)

        with patch.object(log, "_ensure_handle", side_effect=OSError("disk full")):
            import logging
            with caplog.at_level(logging.ERROR):
                log.flush()

        assert any("flush failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Inherited EventLog behavior tests
# ---------------------------------------------------------------------------

class TestInheritedBehavior:

    def test_replay_filters_by_event_type(
        self, tmp_events_dir: Path
    ) -> None:
        """BufferedEventLog should support event_types filter from parent."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        for i in range(4):
            evt = DomainEvent(
                event_type="TRADE" if i % 2 == 0 else "ORDER",
                timestamp=datetime(2026, 1, 15, 9, 15, i, tzinfo=timezone.utc),
                payload={"n": i},
                sequence_number=i,
            )
            log.append(evt)
        log.close()

        replayed = log.replay(event_types={"TRADE"})
        assert len(replayed) == 2
        assert all(e.event_type == "TRADE" for e in replayed)

    def test_replay_filters_by_since(
        self, tmp_events_dir: Path
    ) -> None:
        """BufferedEventLog should support since filter from parent."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        old_evt = DomainEvent(
            event_type="TEST",
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
            payload={"old": True},
            sequence_number=0,
        )
        new_evt = DomainEvent(
            event_type="TEST",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
            payload={"new": True},
            sequence_number=1,
        )
        log.append(old_evt)
        log.append(new_evt)
        log.close()

        replayed = log.replay(since=datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert len(replayed) == 1
        assert replayed[0].payload["new"] is True

    def test_inherited_errors_counter(
        self, tmp_events_dir: Path, sample_event: DomainEvent
    ) -> None:
        """BufferedEventLog should inherit the errors property from EventLog."""
        log = BufferedEventLog(
            events_dir=tmp_events_dir,
            flush_threshold=100,
            flush_interval=10.0,
        )
        assert log.errors == 0
        log.append(sample_event)
        assert log.errors == 0
