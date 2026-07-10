"""Tests for SessionRecorder — the SessionRecording concept from the blueprint."""

from __future__ import annotations

import json

import pytest

from domain.events.types import DomainEvent
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.observability.session_recorder import SessionRecorder


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def test_records_events_for_already_subscribed_types(tmp_path, bus):
    # subscribe_all() only picks up event types that already have at least
    # one subscriber (a documented EventBus limitation, not a recorder
    # bug) -- register a no-op handler for "TICK" first, matching how a
    # real session already has live subscribers before the recorder starts.
    bus.subscribe("TICK", lambda e: None)

    recorder = SessionRecorder(bus, session_id="test-session", output_dir=tmp_path)
    recorder.start()
    bus.publish(DomainEvent.now("TICK", {"ltp": "100.5"}, symbol="RELIANCE"))
    recorder.stop()

    assert recorder.events_written == 1
    assert recorder.write_failures == 0
    lines = recorder.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "TICK"
    assert record["symbol"] == "RELIANCE"
    assert record["payload"]["ltp"] == "100.5"


def test_documented_limitation_misses_event_types_with_no_prior_subscriber(tmp_path, bus):
    """Proves the limitation explicitly rather than hiding it: a type with
    zero subscribers before recorder.start() is not captured, because
    EventBus.subscribe_all() only subscribes to already-registered types."""
    recorder = SessionRecorder(bus, session_id="test-session-2", output_dir=tmp_path)
    recorder.start()
    # No prior subscriber for "QUOTE" existed before start() -> missed.
    bus.publish(DomainEvent.now("QUOTE", {"ltp": "1.0"}))
    recorder.stop()

    assert recorder.events_written == 0


def test_write_failure_is_swallowed_not_raised(tmp_path, bus, monkeypatch):
    bus.subscribe("TICK", lambda e: None)
    recorder = SessionRecorder(bus, session_id="test-session-3", output_dir=tmp_path)
    recorder.start()

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(recorder._path.__class__, "open", _boom)
    # Must not raise, even though the write itself fails.
    bus.publish(DomainEvent.now("TICK", {"ltp": "1.0"}))
    recorder.stop()

    assert recorder.write_failures == 1
    assert recorder.events_written == 0


def test_stop_unsubscribes_no_further_writes(tmp_path, bus):
    bus.subscribe("TICK", lambda e: None)
    recorder = SessionRecorder(bus, session_id="test-session-4", output_dir=tmp_path)
    recorder.start()
    recorder.stop()
    bus.publish(DomainEvent.now("TICK", {"ltp": "1.0"}))
    assert recorder.events_written == 0


def test_start_is_idempotent(tmp_path, bus):
    bus.subscribe("TICK", lambda e: None)
    recorder = SessionRecorder(bus, session_id="test-session-5", output_dir=tmp_path)
    recorder.start()
    recorder.start()  # must not double-subscribe
    bus.publish(DomainEvent.now("TICK", {"ltp": "1.0"}))
    recorder.stop()
    assert recorder.events_written == 1
