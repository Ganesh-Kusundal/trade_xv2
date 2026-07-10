"""B5: Comprehensive immutability tests for DomainEvent.

Verifies:
1. DomainEvent is truly immutable (FrozenInstanceError on all fields)
2. publish() does not mutate original event
3. _prepare_event() creates new instance with injected fields
4. Replay mode preserves original sequence_number
5. EventLog round-trip preserves correlation_id
6. Payload isolation between handlers
7. Naive timestamp rejected with ValueError
"""

from __future__ import annotations

import tempfile
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infrastructure.correlation import with_correlation
from infrastructure.event_bus.event_bus import DomainEvent, EventBus
from infrastructure.event_log import EventLog

# ──────────────────────────────────────────────────────────────────────
# Section 1: DomainEvent is truly immutable
# ──────────────────────────────────────────────────────────────────────


class TestDomainEventImmutability:
    """Verify DomainEvent is frozen and cannot be mutated."""

    def test_event_type_is_immutable(self):
        event = DomainEvent.now("TICK", {"price": 100.0})
        with pytest.raises(FrozenInstanceError):
            event.event_type = "ORDER"

    def test_timestamp_is_immutable(self):
        event = DomainEvent.now("TICK", {})
        with pytest.raises(FrozenInstanceError):
            event.timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_payload_is_immutable(self):
        event = DomainEvent.now("TICK", {"price": 100.0})
        with pytest.raises(FrozenInstanceError):
            event.payload = {"different": "data"}

    def test_symbol_is_immutable(self):
        event = DomainEvent.now("TICK", {}, symbol="RELIANCE")
        with pytest.raises(FrozenInstanceError):
            event.symbol = "TCS"

    def test_source_is_immutable(self):
        event = DomainEvent.now("TICK", {}, source="broker")
        with pytest.raises(FrozenInstanceError):
            event.source = "new_source"

    def test_event_id_is_immutable(self):
        event = DomainEvent.now("TICK", {})
        with pytest.raises(FrozenInstanceError):
            event.event_id = "new_id"

    def test_correlation_id_is_immutable(self):
        event = DomainEvent.now("TICK", {}, correlation_id="corr-123")
        with pytest.raises(FrozenInstanceError):
            event.correlation_id = "corr-456"

    def test_sequence_number_is_immutable(self):
        event = DomainEvent(
            "TICK", datetime(2024, 1, 1, tzinfo=timezone.utc), {}, sequence_number=5
        )
        with pytest.raises(FrozenInstanceError):
            event.sequence_number = 10

    def test_object_setattr_bypasses_frozen_but_our_code_does_not_use_it(self):
        """object.__setattr__ bypasses frozen check in Python — that's why we removed all uses."""
        event = DomainEvent.now("TICK", {})
        # Python allows object.__setattr__ on frozen dataclasses (it bypasses __setattr__)
        # The B5 fix ensures EventBus._prepare_event() uses replace() instead.
        # We verify this by checking the original event is unchanged after publish.
        original_id = id(event)
        original_seq = event.sequence_number

        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))
        bus.publish(event)

        # Original event must be unchanged (proving no object.__setattr__ was used)
        assert id(event) == original_id
        assert event.sequence_number == original_seq
        assert received[0] is not event  # New instance created


# ──────────────────────────────────────────────────────────────────────
# Section 2: publish() does not mutate original event
# ──────────────────────────────────────────────────────────────────────


class TestPublishDoesNotMutate:
    """Verify EventBus.publish() creates a new event instead of mutating."""

    def test_original_event_unchanged_after_publish(self):
        """Original event should retain None correlation_id after publish."""
        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        original = DomainEvent.now("TICK", {"price": 100.0})
        original_correlation_id = original.correlation_id
        original_seq = original.sequence_number

        with with_correlation("test-corr-123"):
            bus.publish(original)

        # Original must be unchanged
        assert original.correlation_id == original_correlation_id, (
            "Original event correlation_id must not change after publish"
        )
        assert original.sequence_number == original_seq, (
            "Original event sequence_number must not change after publish"
        )

        # Received event should have injected fields
        assert len(received) == 1
        assert received[0].correlation_id == "test-corr-123"
        assert received[0].sequence_number > 0

    def test_original_event_is_different_object_after_publish(self):
        """Published event should be a new instance, not the original."""
        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        original = DomainEvent.now("TICK", {"price": 100.0})
        bus.publish(original)

        assert received[0] is not original, (
            "Published event must be a new instance, not the original object"
        )

    def test_original_event_id_preserved(self):
        """event_id must be preserved through copy-on-publish."""
        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        original = DomainEvent.now("TICK", {"price": 100.0})
        bus.publish(original)

        assert received[0].event_id == original.event_id, (
            "event_id must be preserved in the copied event"
        )


# ──────────────────────────────────────────────────────────────────────
# Section 3: _prepare_event() creates new instance
# ──────────────────────────────────────────────────────────────────────


class TestPrepareEvent:
    """Verify _prepare_event() behavior."""

    def test_injects_correlation_id_when_none(self):
        bus = EventBus(fail_fast=False)
        event = DomainEvent.now("TICK", {})
        assert event.correlation_id is None

        with with_correlation("corr-from-context"):
            prepared = bus._prepare_event(event)

        assert prepared.correlation_id == "corr-from-context"
        assert event.correlation_id is None  # Original unchanged

    def test_preserves_existing_correlation_id(self):
        bus = EventBus(fail_fast=False)
        event = DomainEvent.now("TICK", {}, correlation_id="existing-corr")

        with with_correlation("different-corr"):
            prepared = bus._prepare_event(event)

        assert prepared.correlation_id == "existing-corr"

    def test_assigns_sequence_number_in_live_mode(self):
        bus = EventBus(fail_fast=False)
        event = DomainEvent("TICK", datetime(2024, 1, 1, tzinfo=timezone.utc), {})
        assert event.sequence_number == 0

        prepared = bus._prepare_event(event)

        assert prepared.sequence_number == 1
        assert event.sequence_number == 0  # Original unchanged

    def test_preserves_sequence_number_in_replay_mode(self):
        bus = EventBus(fail_fast=False, replay_mode=True)
        event = DomainEvent(
            "TICK",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            {},
            sequence_number=42,
        )

        prepared = bus._prepare_event(event)

        assert prepared.sequence_number == 42
        assert event.sequence_number == 42

    def test_returns_original_when_no_changes_needed(self):
        """Optimization: return same object when no replacements needed."""
        bus = EventBus(fail_fast=False, replay_mode=True)
        event = DomainEvent(
            "TICK",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            {},
            correlation_id="already-set",
            sequence_number=5,
        )

        prepared = bus._prepare_event(event)

        assert prepared is event, "_prepare_event should return original when no changes needed"

    def test_creates_new_instance_when_changes_needed(self):
        bus = EventBus(fail_fast=False)
        event = DomainEvent.now("TICK", {})

        prepared = bus._prepare_event(event)

        assert prepared is not event, (
            "_prepare_event must create new instance when injecting fields"
        )


# ──────────────────────────────────────────────────────────────────────
# Section 4: Replay mode preserves original values
# ──────────────────────────────────────────────────────────────────────


class TestReplayModePreservation:
    """Verify replay mode preserves original event values."""

    def test_replay_mode_preserves_sequence_numbers(self):
        """In replay mode, _prepare_event preserves original sequence_number."""
        bus = EventBus(fail_fast=False, replay_mode=True)

        events = [
            DomainEvent("TICK", datetime(2024, 1, 1, tzinfo=timezone.utc), {}, sequence_number=5),
            DomainEvent("TICK", datetime(2024, 1, 2, tzinfo=timezone.utc), {}, sequence_number=3),
            DomainEvent("TICK", datetime(2024, 1, 3, tzinfo=timezone.utc), {}, sequence_number=8),
        ]

        # _prepare_event is the method that handles sequence number logic
        prepared = [bus._prepare_event(e) for e in events]

        seqs = [e.sequence_number for e in prepared]
        assert seqs == [5, 3, 8], "Replay mode must preserve original sequence numbers"

    def test_replay_mode_does_not_assign_new_sequence(self):
        """In replay mode, _prepare_event does not assign new sequence numbers."""
        bus = EventBus(fail_fast=False, replay_mode=True)

        event = DomainEvent(
            "TICK", datetime(2024, 1, 1, tzinfo=timezone.utc), {}, sequence_number=0
        )
        prepared = bus._prepare_event(event)

        assert prepared.sequence_number == 0, "Replay mode must not assign new sequence numbers"
        assert prepared is event  # No changes needed, returns original

    def test_live_mode_assigns_monotonic_sequence(self):
        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        for _ in range(5):
            bus.publish(DomainEvent.now("TICK", {}))

        seqs = [e.sequence_number for e in received]
        assert seqs == [1, 2, 3, 4, 5], (
            "Live mode must assign monotonically increasing sequence numbers"
        )


# ──────────────────────────────────────────────────────────────────────
# Section 5: EventLog round-trip preserves correlation_id
# ──────────────────────────────────────────────────────────────────────


class TestEventLogRoundTrip:
    """Verify EventLog serialization preserves correlation_id."""

    def test_append_and_replay_preserves_correlation_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = EventLog(events_dir=Path(tmpdir))
            try:
                event = DomainEvent(
                    "TICK",
                    datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                    {"price": 100.0},
                    symbol="RELIANCE",
                    correlation_id="corr-roundtrip-123",
                    sequence_number=42,
                )
                log.append(event)
                log.close()

                replayed = log.replay()
                assert len(replayed) == 1
                assert replayed[0].correlation_id == "corr-roundtrip-123", (
                    "EventLog round-trip must preserve correlation_id"
                )
            finally:
                log.close()

    def test_append_and_replay_preserves_sequence_number(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = EventLog(events_dir=Path(tmpdir))
            try:
                event = DomainEvent(
                    "ORDER",
                    datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                    {},
                    sequence_number=99,
                )
                log.append(event)
                log.close()

                replayed = log.replay()
                assert len(replayed) == 1
                assert replayed[0].sequence_number == 99, (
                    "EventLog round-trip must preserve sequence_number"
                )
            finally:
                log.close()

    def test_replay_with_none_correlation_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = EventLog(events_dir=Path(tmpdir))
            try:
                event = DomainEvent(
                    "TICK",
                    datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                    {},
                    correlation_id=None,
                )
                log.append(event)
                log.close()

                replayed = log.replay()
                assert len(replayed) == 1
                assert replayed[0].correlation_id is None, (
                    "EventLog round-trip must preserve None correlation_id"
                )
            finally:
                log.close()


# ──────────────────────────────────────────────────────────────────────
# Section 6: Payload isolation between handlers
# ──────────────────────────────────────────────────────────────────────


class TestPayloadIsolation:
    """Verify payload defensive copy prevents handler mutation."""

    def test_factory_creates_defensive_copy(self):
        """DomainEvent.now() should create a shallow copy of payload."""
        original_payload = {"price": 100.0}
        event = DomainEvent.now("TICK", original_payload)

        # Mutating original dict should not affect event payload
        original_payload["price"] = 999.0
        assert event.payload["price"] == 100.0, (
            "DomainEvent.now() must create defensive copy of payload"
        )

    def test_handler_cannot_mutate_shared_payload(self):
        """Payload is frozen: mutation fails and peer handlers still receive the event."""
        bus = EventBus(fail_fast=False)
        payloads_seen = []
        mutations_blocked = []

        def handler1(event):
            try:
                event.payload["modified"] = True  # type: ignore[index]
                mutations_blocked.append(False)
            except (TypeError, AttributeError):
                mutations_blocked.append(True)
            payloads_seen.append(dict(event.payload))

        def handler2(event):
            payloads_seen.append(dict(event.payload))

        bus.subscribe("TICK", handler1)
        bus.subscribe("TICK", handler2)

        bus.publish(DomainEvent.now("TICK", {"price": 100.0}))

        # Both handlers run; mutation is rejected (mappingproxy / frozen payload).
        assert len(payloads_seen) == 2
        assert mutations_blocked == [True]
        assert "modified" not in payloads_seen[1]
        assert payloads_seen[0]["price"] == 100.0

    def test_payload_is_dict_not_original_reference(self):
        original = {"data": [1, 2, 3]}
        event = DomainEvent.now("TICK", original)

        assert event.payload is not original, (
            "Event payload must be a copy, not the original reference"
        )


# ──────────────────────────────────────────────────────────────────────
# Section 7: Naive timestamp rejected
# ──────────────────────────────────────────────────────────────────────


class TestNaiveTimestampRejection:
    """Verify naive timestamps are rejected with ValueError."""

    def test_naive_timestamp_raises_value_error(self):
        naive_ts = datetime(2024, 1, 1, 12, 0, 0)

        with pytest.raises(ValueError, match="timezone-aware"):
            DomainEvent(
                event_type="TICK",
                timestamp=naive_ts,
                payload={"price": 100.0},
            )

    def test_utc_aware_timestamp_accepted(self):
        utc_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        event = DomainEvent(
            event_type="TICK",
            timestamp=utc_ts,
            payload={"price": 100.0},
        )
        assert event.timestamp.tzinfo is not None

    def test_factory_always_produces_aware_timestamp(self):
        event = DomainEvent.now("TICK", {})
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == timezone.utc

    def test_error_message_is_helpful(self):
        naive_ts = datetime(2024, 1, 1)
        with pytest.raises(ValueError) as exc_info:
            DomainEvent("TICK", naive_ts, {})

        error_msg = str(exc_info.value)
        assert "timezone-aware" in error_msg
        assert "DomainEvent.now()" in error_msg


# ──────────────────────────────────────────────────────────────────────
# Section 8: Integration - full publish lifecycle
# ──────────────────────────────────────────────────────────────────────


class TestPublishLifecycle:
    """Integration tests for the full publish lifecycle."""

    def test_full_lifecycle_immutability_preserved(self):
        """Complete publish flow: event remains immutable throughout."""
        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        original_payload = {"price": 100.0}
        original = DomainEvent.now("TICK", original_payload)

        # Record original state
        orig_event_id = original.event_id
        orig_correlation = original.correlation_id
        orig_seq = original.sequence_number
        orig_payload = dict(original.payload)

        with with_correlation("lifecycle-test"):
            bus.publish(original)

        # Verify original is unchanged
        assert original.event_id == orig_event_id
        assert original.correlation_id == orig_correlation
        assert original.sequence_number == orig_seq
        assert original.payload == orig_payload

        # Verify received event has injected fields
        assert len(received) == 1
        assert received[0].correlation_id == "lifecycle-test"
        assert received[0].sequence_number > 0
        assert received[0].event_id == orig_event_id

    def test_multiple_publishes_independent(self):
        """Multiple publishes of the same event are deduplicated by idempotency."""
        bus = EventBus(fail_fast=False)
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        original = DomainEvent.now("TICK", {"price": 100.0})
        bus.publish(original)
        bus.publish(original)
        bus.publish(original)

        # Idempotency: same event_id → only first delivery counts
        assert len(received) == 1
        assert received[0].event_id == original.event_id
