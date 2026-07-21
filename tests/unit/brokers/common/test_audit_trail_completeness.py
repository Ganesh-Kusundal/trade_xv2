"""Audit trail completeness — every order lifecycle event is queryable.

A user trusts the system only if every order action leaves a trace.
These tests verify that the critical order lifecycle events are
persisted and retrievable, regardless of internal implementation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from infrastructure.event_bus import DomainEvent, EventBus
from infrastructure.event_log import EventLog


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "events"


ORDER_LIFECYCLE_EVENTS = [
    "ORDER_PLACED",
    "ORDER_SUBMITTED",
    "ORDER_UPDATED",
    "ORDER_CANCELLED",
    "ORDER_REJECTED",
    "TRADE",
    "TRADE_FILLED",
    "TRADE_APPLIED",
]


class TestAuditTrailCompleteness:
    """Every order lifecycle event is persisted and queryable."""

    @pytest.mark.parametrize("event_type", ORDER_LIFECYCLE_EVENTS)
    def test_order_lifecycle_event_is_persisted(self, log_dir: Path, event_type: str) -> None:
        log = EventLog(events_dir=log_dir)
        event = DomainEvent.now(event_type, {"order_id": "O1"}, symbol="RELIANCE")
        log.append(event)
        log.close()

        replayed = log.replay(event_types={event_type})
        assert len(replayed) == 1
        assert replayed[0].event_type == event_type

    def test_full_order_lifecycle_is_replayable(self, log_dir: Path) -> None:
        """Place → submit → update → fill → trade applied — all in sequence."""
        log = EventLog(events_dir=log_dir)
        sequence = [
            ("ORDER_PLACED", {"order_id": "O1", "action": "place"}),
            ("ORDER_SUBMITTED", {"order_id": "O1", "action": "submit"}),
            ("ORDER_UPDATED", {"order_id": "O1", "action": "modify"}),
            ("TRADE", {"order_id": "O1", "trade_id": "T1", "action": "trade"}),
            ("TRADE_FILLED", {"order_id": "O1", "trade_id": "T1", "action": "fill"}),
            ("TRADE_APPLIED", {"order_id": "O1", "trade_id": "T1", "action": "apply"}),
        ]
        for event_type, payload in sequence:
            log.append(DomainEvent.now(event_type, payload, symbol="RELIANCE"))
        log.close()

        replayed = log.replay()
        assert len(replayed) == len(sequence)
        for original, persisted in zip(sequence, replayed):
            assert persisted.event_type == original[0]
            assert persisted.payload["order_id"] == "O1"

    def test_audit_trail_survives_filtering_by_time(self, log_dir: Path) -> None:
        """Events from different days are still queryable by time range."""
        log = EventLog(events_dir=log_dir)

        old_event = DomainEvent(
            event_type="ORDER_PLACED",
            timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            payload={"order_id": "OLD"},
        )
        new_event = DomainEvent(
            event_type="ORDER_CANCELLED",
            timestamp=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
            payload={"order_id": "NEW"},
        )
        log.append(old_event)
        log.append(new_event)
        log.close()

        recent = log.replay(since=datetime(2025, 3, 1, tzinfo=timezone.utc))
        assert len(recent) == 1
        assert recent[0].payload["order_id"] == "NEW"

    def test_multiple_orders_dont_cross_contaminate(self, log_dir: Path) -> None:
        """Filtering by event_type returns only matching events."""
        log = EventLog(events_dir=log_dir)
        log.append(DomainEvent.now("ORDER_PLACED", {"order_id": "O1"}))
        log.append(DomainEvent.now("TRADE", {"order_id": "O1", "trade_id": "T1"}))
        log.append(DomainEvent.now("ORDER_PLACED", {"order_id": "O2"}))
        log.close()

        placed = log.replay(event_types={"ORDER_PLACED"})
        assert len(placed) == 2

        trades = log.replay(event_types={"TRADE"})
        assert len(trades) == 1
        assert trades[0].payload["trade_id"] == "T1"
