"""Architecture tests: assert exactly ONE authority for retry and idempotency.

DR-I1: a single ``RetryExecutor`` class definition.
DR-I2: a single ``IdempotencyService`` class definition, and the EventBus
delegates its event-dedup to it (no double-write to two independent stores).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from domain.events.types import DomainEvent
from infrastructure.event_bus.event_bus import EventBus
from infrastructure.idempotency import IdempotencyService, MemoryIdempotencyCache

SRC = Path(__file__).resolve().parents[4] / "src"

RETRY_DEF_RE = re.compile(r"^class RetryExecutor\b", re.MULTILINE)
IDEMPOTENCY_DEF_RE = re.compile(r"^class IdempotencyService\b", re.MULTILINE)


def _src_py_files():
    return [p for p in SRC.rglob("*.py")]


def test_exactly_one_retry_executor_definition():
    matches = [
        str(p)
        for p in _src_py_files()
        if RETRY_DEF_RE.search(p.read_text())
    ]
    assert matches == [str(SRC / "infrastructure/resilience/retry_executor.py")], (
        f"Expected exactly one RetryExecutor definition; found: {matches}"
    )


def test_exactly_one_idempotency_service_definition():
    matches = [
        str(p)
        for p in _src_py_files()
        if IDEMPOTENCY_DEF_RE.search(p.read_text())
    ]
    assert matches == [str(SRC / "infrastructure/idempotency/service.py")], (
        f"Expected exactly one IdempotencyService definition; found: {matches}"
    )


def test_event_bus_delegates_dedup_to_idempotency_service():
    # EventBus must reference the single IdempotencyService authority.
    bus_src = (SRC / "infrastructure/event_bus/event_bus.py").read_text()
    assert "IdempotencyService" in bus_src, (
        "EventBus should delegate dedup to IdempotencyService"
    )

    service = IdempotencyService(MemoryIdempotencyCache())
    bus = EventBus(idempotency=service)

    seen: list[DomainEvent] = []
    bus.subscribe("TICK", seen.append)

    def make(eid: str) -> DomainEvent:
        return DomainEvent(
            event_type="TICK",
            timestamp=datetime.now(timezone.utc),
            payload={"x": 1},
            symbol="A",
            event_id=eid,
        )

    bus.publish(make("dup-1"))
    bus.publish(make("dup-1"))  # duplicate event_id -> must be skipped

    assert len(seen) == 1, "duplicate event must be de-duplicated via IdempotencyService"

    # Single authority: when a service is wired, the local fallback set must
    # NOT be written (no double-write to two independent dedup stores).
    assert len(bus._processed_event_ids) == 0
    assert len(bus._processed_events) == 0


def test_event_bus_fallback_dedup_without_service():
    # Without a service, the local bounded set remains the (degraded) fallback.
    bus = EventBus()

    seen: list[DomainEvent] = []
    bus.subscribe("TICK", seen.append)

    def make(eid: str) -> DomainEvent:
        return DomainEvent(
            event_type="TICK",
            timestamp=datetime.now(timezone.utc),
            payload={"x": 1},
            symbol="A",
            event_id=eid,
        )

    bus.publish(make("dup-2"))
    bus.publish(make("dup-2"))

    assert len(seen) == 1
    assert len(bus._processed_event_ids) == 1
