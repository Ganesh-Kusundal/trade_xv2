"""EventLog daily-rotation unit tests.

The EventLog writes one JSONL file per UTC day under ``events_dir``
named ``YYYY-MM-DD.jsonl``. The daily-rotation logic is exercised by
appending events with timestamps on different days and verifying the
files split correctly, replay returns the events in insertion order,
and a corrupt line in any single file does not poison the others.

Complements the chaos-level test in
``tests/chaos/test_recovery_certification.py::test_scenario_3`` with
focused assertions on the rotation behaviour.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from infrastructure.event_bus import DomainEvent, EventType
from brokers.common.event_log import EventLog


def _event(event_type: str, ts: datetime) -> DomainEvent:
    return DomainEvent(
        event_type=event_type,
        timestamp=ts,
        payload={"v": 1},
        symbol="RELIANCE",
        source="test",
    )


def test_event_log_creates_daily_files(tmp_path: Path) -> None:
    log = EventLog(events_dir=tmp_path / "events")
    try:
        day1 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
        day3 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)
        log.append(_event("ORDER_PLACED", day1))
        log.append(_event("ORDER_PLACED", day2))
        log.append(_event("ORDER_PLACED", day3))
    finally:
        log.close()

    files = sorted(p.name for p in (tmp_path / "events").iterdir())
    assert files == ["2026-06-15.jsonl", "2026-06-16.jsonl", "2026-06-17.jsonl"]


def test_event_log_replay_preserves_insertion_order_across_days(tmp_path: Path) -> None:
    log = EventLog(events_dir=tmp_path / "events")
    try:
        day1 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 6, 16, 11, 0, tzinfo=timezone.utc)
        day3 = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
        log.append(_event("E1", day1))
        log.append(_event("E2", day2))
        log.append(_event("E3", day3))
    finally:
        log.close()

    events = EventLog(events_dir=tmp_path / "events").replay()
    assert [e.event_type for e in events] == ["E1", "E2", "E3"]


def test_event_log_replay_skips_corrupt_line(tmp_path: Path) -> None:
    log = EventLog(events_dir=tmp_path / "events")
    try:
        day1 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        log.append(_event("E1", day1))
    finally:
        log.close()

    # Append a corrupt line to the same day file.
    log_file = tmp_path / "events" / "2026-06-15.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write('{"event_type":"E2","trunca')

    events = EventLog(events_dir=tmp_path / "events").replay()
    assert [e.event_type for e in events] == ["E1"]


def test_event_log_replay_filters_by_event_type(tmp_path: Path) -> None:
    log = EventLog(events_dir=tmp_path / "events")
    try:
        day1 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        log.append(_event("ORDER_PLACED", day1))
        log.append(_event(EventType.TRADE.value, day1))  # P1-3: Migrated to EventType enum
        log.append(_event(EventType.ORDER_UPDATED.value, day1))  # P1-3: Migrated to EventType enum
    finally:
        log.close()

    events = EventLog(events_dir=tmp_path / "events").replay(event_types={EventType.TRADE.value})  # P1-3: Migrated to EventType enum
    assert [e.event_type for e in events] == ["TRADE"]


def test_event_log_replay_filters_by_since(tmp_path: Path) -> None:
    log = EventLog(events_dir=tmp_path / "events")
    try:
        t1 = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
        log.append(_event("E1", t1))
        log.append(_event("E2", t2))
        log.append(_event("E3", t3))
    finally:
        log.close()

    cutoff = datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc)
    events = EventLog(events_dir=tmp_path / "events").replay(since=cutoff)
    assert [e.event_type for e in events] == ["E2", "E3"]


def test_event_log_uses_local_date_for_rotation(tmp_path: Path) -> None:
    """The rotation is based on the date of the event's timestamp
    (UTC by convention), not on the wall clock at append time. Two
    events on different UTC days always go to different files.
    """
    log = EventLog(events_dir=tmp_path / "events")
    try:
        late_utc_day = datetime(2026, 6, 15, 23, 30, tzinfo=timezone.utc)
        early_utc_day = datetime(2026, 6, 16, 0, 30, tzinfo=timezone.utc)
        log.append(_event("LATE", late_utc_day))
        log.append(_event("EARLY", early_utc_day))
    finally:
        log.close()

    files = sorted(p.name for p in (tmp_path / "events").iterdir())
    assert files == ["2026-06-15.jsonl", "2026-06-16.jsonl"]


def test_event_log_replay_empty_dir_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "events").mkdir(parents=True, exist_ok=True)
    events = EventLog(events_dir=tmp_path / "events").replay()
    assert events == []


def test_event_log_replay_collects_across_multiple_corrupt_files(tmp_path: Path) -> None:
    """A corrupt line in one day's file must not block replay of a
    later day's file. Both must be replayable independently.
    """
    log = EventLog(events_dir=tmp_path / "events")
    try:
        log.append(_event("A", datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)))
        log.append(_event("B", datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)))
        log.append(_event("C", datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)))
    finally:
        log.close()

    # Inject a corrupt line in the middle day.
    day2 = tmp_path / "events" / "2026-06-16.jsonl"
    with day2.open("a", encoding="utf-8") as f:
        f.write("NOT_JSON\n")

    events = EventLog(events_dir=tmp_path / "events").replay()
    assert [e.event_type for e in events] == ["A", "B", "C"]
