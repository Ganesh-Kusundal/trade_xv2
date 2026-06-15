"""Tests for the hardened EventBus.

These cover the three Phase 1 deliverables:

1. Handler failures are NEVER silently swallowed — they are logged,
   counted, and dead-lettered.
2. Missing DLQ produces a loud error, not a silent drop.
3. EventLog failures are surfaced and dead-lettered.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from brokers.common.event_bus import (
    DeadLetterQueue,
    DomainEvent,
    EventBus,
)
from brokers.common.observability.event_metrics import EventMetrics


def _event(payload: dict | None = None) -> DomainEvent:
    return DomainEvent.now("TICK", payload or {"ltp": 100.0}, symbol="RELIANCE")


def test_publish_invokes_all_handlers() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("TICK", lambda e: seen.append(e.event_id))
    bus.subscribe("TICK", lambda e: seen.append(e.event_id + "!"))
    bus.publish(_event())
    assert len(seen) == 2


def test_publish_dispatches_to_event_type_only() -> None:
    bus = EventBus()
    tick_seen: list[DomainEvent] = []
    quote_seen: list[DomainEvent] = []
    bus.subscribe("TICK", tick_seen.append)
    bus.subscribe("QUOTE", quote_seen.append)
    bus.publish(_event())
    assert len(tick_seen) == 1
    assert quote_seen == []


def test_handler_exception_is_logged_counted_and_dead_lettered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    metrics = EventMetrics()
    dlq = DeadLetterQueue()
    bus = EventBus(metrics=metrics, dead_letter_queue=dlq)

    def boom(_event: DomainEvent) -> None:
        raise RuntimeError("kaboom")

    bus.subscribe("TICK", boom)
    with caplog.at_level(logging.WARNING):
        bus.publish(_event())

    # Visible in metrics
    assert metrics.get("TICK", "dispatched") == 1
    assert metrics.get("TICK", "handler_error:RuntimeError") == 1
    assert metrics.get("TICK", "dead_letter") == 1

    # Captured in DLQ
    assert len(dlq) == 1
    dead = dlq.peek()[0]
    assert dead.handler_id != ""
    assert dead.error_type == "RuntimeError"
    assert "kaboom" in dead.error_message

    # Logged with full context
    assert any("kaboom" in r.message for r in caplog.records)


def test_handler_exception_does_not_stop_other_handlers() -> None:
    bus = EventBus()
    received: list[str] = []

    bus.subscribe("TICK", lambda e: received.append("first"))

    def boom(_e: DomainEvent) -> None:
        raise RuntimeError("nope")

    bus.subscribe("TICK", boom)
    bus.subscribe("TICK", lambda e: received.append("third"))

    bus.publish(_event())

    # Second handler raised, but first and third still ran.
    assert received == ["first", "third"]


def test_missing_dead_letter_queue_logs_error() -> None:
    """Without a DLQ attached, a handler failure must be loudly visible."""
    bus = EventBus(fail_fast=True)  # no DLQ
    bus.subscribe("TICK", lambda e: (_ for _ in ()).throw(RuntimeError("x")))

    with pytest.raises(RuntimeError):
        bus.publish(_event())


def test_missing_dlq_logs_loud_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()  # no DLQ
    bus.subscribe("TICK", lambda e: (_ for _ in ()).throw(RuntimeError("nope")))

    with caplog.at_level(logging.ERROR):
        bus.publish(_event())

    # The "no DLQ" configuration error is loudly logged at ERROR.
    assert any("DeadLetterQueue" in r.message for r in caplog.records)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_publish_failure_is_counted_and_dead_lettered() -> None:
    metrics = EventMetrics()
    dlq = DeadLetterQueue()
    bus = EventBus(metrics=metrics, dead_letter_queue=dlq)

    # Replace the bus's _event_log with a mock that raises on append.
    fake_log = MagicMock()
    fake_log.append.side_effect = OSError("disk full")
    bus._event_log = fake_log

    bus.subscribe("TICK", lambda e: None)
    bus.publish(_event())

    assert metrics.get("TICK", "log_error:OSError") == 1
    # The log failure itself is captured in the DLQ.
    assert len(dlq) == 1
    assert dlq.peek()[0].handler_id == "<event_log>"


def test_publish_does_not_silently_swallow_log_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    fake_log = MagicMock()
    fake_log.append.side_effect = OSError("disk full")
    bus._event_log = fake_log
    bus.subscribe("TICK", lambda e: None)

    with caplog.at_level(logging.ERROR):
        bus.publish(_event())

    assert any("disk full" in r.message for r in caplog.records)


def test_fail_fast_propagates_handler_exceptions() -> None:
    bus = EventBus(fail_fast=True)
    bus.subscribe("TICK", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        bus.publish(_event())


def test_metrics_record_publish_and_dispatch() -> None:
    metrics = EventMetrics()
    bus = EventBus(metrics=metrics)
    bus.subscribe("TICK", lambda e: None)
    bus.publish(_event())
    bus.publish(_event())
    assert metrics.get("TICK", "published") == 2
    assert metrics.get("TICK", "dispatched") == 2


def test_subscribe_returns_unique_token() -> None:
    bus = EventBus()
    t1 = bus.subscribe("TICK", lambda e: None)
    t2 = bus.subscribe("TICK", lambda e: None)
    assert t1 != t2
    assert bus.subscriber_count("TICK") == 2
    assert bus.unsubscribe(t1) is True
    assert bus.subscriber_count("TICK") == 1


def test_unsubscribe_unknown_token_returns_false() -> None:
    bus = EventBus()
    assert bus.unsubscribe("nope") is False


def test_clear_removes_all_subscribers() -> None:
    bus = EventBus()
    bus.subscribe("TICK", lambda e: None)
    bus.subscribe("QUOTE", lambda e: None)
    bus.clear()
    assert bus.subscriber_count() == 0
