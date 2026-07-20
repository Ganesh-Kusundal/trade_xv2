"""IP-5: EventBus Domain Event Flow integration tests.

Verifies end-to-end event bus behaviour: fan-out dispatch, dead-letter
routing, event-log persistence, ordering guarantees, bounded DLQ,
metrics recording, idempotent writes, and persistent DLQ durability.

All tests use REAL infrastructure objects — no mocks.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infrastructure.event_bus import DomainEvent, EventBus, EventBusConfig
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from infrastructure.event_bus.persistent_dead_letter_queue import (
    PersistentDeadLetterQueue,
)
from infrastructure.event_log import EventLog
from infrastructure.observability.event_metrics import EventMetrics

pytestmark = pytest.mark.integration


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_event(
    event_type: str = "ORDER_PLACED",
    event_id: str = "evt-1",
    sequence_number: int = 0,
) -> DomainEvent:
    """Create a domain event for testing."""
    return DomainEvent(
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        payload={"order_id": f"ORD-{event_id}", "symbol": "RELIANCE"},
        symbol="RELIANCE",
        event_id=event_id,
        sequence_number=sequence_number,
    )


# ── Fixtures (function-scoped → fresh per test) ───────────────────────────


@pytest.fixture()
def event_log(tmp_path: Path) -> EventLog:
    """Function-scoped EventLog backed by a temp directory."""
    return EventLog(events_dir=tmp_path / "events")


@pytest.fixture()
def event_bus(event_log: EventLog) -> EventBus:
    """Function-scoped EventBus wired to a real EventLog."""
    return EventBus(
        event_log=event_log, config=EventBusConfig(logging_enabled=False, fail_fast=False)
    )


# ── 1. Fan-out correctness ───────────────────────────────────────────────


def test_event_reaches_all_subscribers(event_bus: EventBus) -> None:
    """EventBus delivers every published event to all registered handlers."""
    received_a: list[str] = []
    received_b: list[str] = []
    received_c: list[str] = []

    event_bus.subscribe("ORDER_PLACED", lambda e: received_a.append(e.event_id))
    event_bus.subscribe("ORDER_PLACED", lambda e: received_b.append(e.event_id))
    event_bus.subscribe("ORDER_PLACED", lambda e: received_c.append(e.event_id))

    event = _make_event(event_id="evt-fanout")
    event_bus.publish(event)

    assert len(received_a) == 1
    assert len(received_b) == 1
    assert len(received_c) == 1
    assert received_a[0] == "evt-fanout"
    assert received_b[0] == "evt-fanout"
    assert received_c[0] == "evt-fanout"


# ── 2. Failed handler → DLQ ──────────────────────────────────────────────


def test_handler_exception_routes_to_dlq() -> None:
    """A handler that raises is caught and the event lands in the DLQ."""
    dlq = DeadLetterQueue(max_size=100)
    bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

    def bad_handler(event: DomainEvent) -> None:
        raise ValueError("simulated handler crash")

    bus.subscribe("ORDER_PLACED", bad_handler)

    event = _make_event(event_id="evt-dlq")
    bus.publish(event)

    assert len(dlq) == 1
    dead_letter = dlq.peek(1)[0]
    assert dead_letter.event.event_id == "evt-dlq"
    assert dead_letter.error_type == "ValueError"
    assert "simulated handler crash" in dead_letter.error_message


# ── 3. EventLog persists to JSONL ────────────────────────────────────────


def test_event_log_persists_event(event_log: EventLog, tmp_path: Path) -> None:
    """EventLog.append() writes a readable JSONL record to disk."""
    event = _make_event(event_id="evt-persist")
    event_log.append(event)
    event_log.close()

    events_dir = tmp_path / "events"
    jsonl_files = list(events_dir.glob("*.jsonl"))
    assert len(jsonl_files) == 1

    lines = jsonl_files[0].read_text().strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["event_type"] == "ORDER_PLACED"
    assert record["symbol"] == "RELIANCE"
    assert "timestamp" in record


# ── 4. Sequence numbers maintain order ───────────────────────────────────


def test_event_ordering_preserved(event_bus: EventBus) -> None:
    """EventBus assigns monotonically increasing sequence numbers."""
    captured: list[DomainEvent] = []
    event_bus.subscribe("ORDER_PLACED", lambda e: captured.append(e))

    for i in range(5):
        event_bus.publish(_make_event(event_id=f"evt-ord-{i}"))

    assert len(captured) == 5
    seq_nums = [e.sequence_number for e in captured]

    # Every sequence number must be strictly greater than the previous.
    for i in range(1, len(seq_nums)):
        assert seq_nums[i] > seq_nums[i - 1]

    # All unique.
    assert len(set(seq_nums)) == 5


# ── 5. DLQ max_size enforced ─────────────────────────────────────────────


def test_dlq_size_bounded() -> None:
    """DeadLetterQueue drops oldest entries when capacity is exceeded."""
    dlq = DeadLetterQueue(max_size=3)
    bus = EventBus(dead_letter_queue=dlq, config=EventBusConfig(fail_fast=False))

    bus.subscribe("ORDER_PLACED", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))

    for i in range(5):
        bus.publish(_make_event(event_id=f"evt-bounded-{i}"))

    assert len(dlq) == 3
    assert dlq.dropped == 2

    remaining_ids = [dl.event.event_id for dl in dlq.peek(10)]
    # Oldest two events were evicted.
    assert "evt-bounded-0" not in remaining_ids
    assert "evt-bounded-1" not in remaining_ids
    # Newest three survived.
    assert "evt-bounded-2" in remaining_ids
    assert "evt-bounded-3" in remaining_ids
    assert "evt-bounded-4" in remaining_ids


# ── 6. EventMetrics counters ─────────────────────────────────────────────


def test_event_metrics_recorded() -> None:
    """EventBus increments published / dispatched counters on EventMetrics."""
    metrics = EventMetrics()
    bus = EventBus(metrics=metrics, config=EventBusConfig(fail_fast=False))

    bus.subscribe("ORDER_PLACED", lambda e: None)
    bus.subscribe("ORDER_PLACED", lambda e: None)

    bus.publish(_make_event(event_id="evt-metrics"))

    # 1 publish + 2 dispatches (one per subscriber).
    assert metrics.get("ORDER_PLACED", "published") == 1
    assert metrics.get("ORDER_PLACED", "dispatched") == 2


# ── 7. Idempotent event-log write ────────────────────────────────────────


def test_idempotent_event_log_write(event_log: EventLog, tmp_path: Path) -> None:
    """Appending the same event twice does not create duplicate log entries."""
    event = _make_event(event_id="evt-idem")

    event_log.append(event)
    event_log.append(event)  # duplicate — must be silently ignored
    event_log.close()

    events_dir = tmp_path / "events"
    jsonl_files = list(events_dir.glob("*.jsonl"))
    assert len(jsonl_files) == 1

    lines = [ln for ln in jsonl_files[0].read_text().strip().splitlines() if ln.strip()]
    # Only ONE entry despite two append() calls.
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["event_type"] == "ORDER_PLACED"


# ── 8. PersistentDLQ survives restart ────────────────────────────────────


def test_dead_letter_queue_persistent(tmp_path: Path) -> None:
    """PersistentDeadLetterQueue reloads dead letters after re-instantiation."""
    db_path = tmp_path / "dlq.sqlite"

    # --- "first process" ---
    dlq1 = PersistentDeadLetterQueue(max_size=100, db_path=db_path)
    bus1 = EventBus(dead_letter_queue=dlq1, config=EventBusConfig(fail_fast=False))
    bus1.subscribe("ORDER_PLACED", lambda e: (_ for _ in ()).throw(RuntimeError("fatal")))

    bus1.publish(_make_event(event_id="evt-persist-dlq"))
    assert len(dlq1) == 1

    # --- "restart" — fresh instance, same DB ---
    dlq2 = PersistentDeadLetterQueue(max_size=100, db_path=db_path)
    loaded = dlq2.load_recent(limit=10)

    assert len(loaded) >= 1
    event_ids = [dl.event.event_id for dl in loaded]
    assert "evt-persist-dlq" in event_ids
    assert loaded[0].error_type == "RuntimeError"
