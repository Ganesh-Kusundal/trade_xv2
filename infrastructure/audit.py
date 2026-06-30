"""Persistent, queryable audit trail for the TradeXV2 platform.

Provides structured audit event storage with in-memory and JSONL file-backed
implementations, plus an AuditLogger facade that auto-fills timestamps and
correlation IDs.

Usage:
    from infrastructure.audit import audit_logger

    audit_logger.log(
        event_type="order.placed",
        actor="user:123",
        action="create",
        resource_type="order",
        resource_id="ORD-456",
        details={"symbol": "RELIANCE", "qty": 10},
    )
"""

from __future__ import annotations

import json
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infrastructure.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Audit event dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEvent:
    """A single immutable audit trail record."""

    event_id: str
    timestamp: str
    event_type: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    correlation_id: str
    ip_address: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Abstract store
# ---------------------------------------------------------------------------

class AuditStore(ABC):
    """Abstract base for audit event persistence."""

    @abstractmethod
    def append(self, event: AuditEvent) -> None: ...

    @abstractmethod
    def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...

    @abstractmethod
    def get(self, event_id: str) -> AuditEvent | None: ...

    @abstractmethod
    def count(self, event_type: str | None = None) -> int: ...

    @abstractmethod
    def clear(self) -> None: ...


# ---------------------------------------------------------------------------
# In-memory store (thread-safe)
# ---------------------------------------------------------------------------

class MemoryAuditStore(AuditStore):
    """Thread-safe in-memory audit store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def get(self, event_id: str) -> AuditEvent | None:
        with self._lock:
            for e in self._events:
                if e.event_id == event_id:
                    return e
        return None

    def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        with self._lock:
            snapshot = list(self._events)

        results: list[AuditEvent] = []
        for e in snapshot:
            if event_type is not None and e.event_type != event_type:
                continue
            if actor is not None and e.actor != actor:
                continue
            if from_time is not None and e.timestamp < from_time:
                continue
            if to_time is not None and e.timestamp > to_time:
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    def count(self, event_type: str | None = None) -> int:
        with self._lock:
            if event_type is not None:
                return sum(1 for e in self._events if e.event_type == event_type)
            return len(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


# ---------------------------------------------------------------------------
# JSONL file-backed store
# ---------------------------------------------------------------------------

class FileAuditStore(AuditStore):
    """Append-only JSONL file-backed audit store.

    Reads are performed by scanning the file on each query.  Writes are
    append-only with a per-file lock to avoid interleaved lines from
    concurrent writers.
    """

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._write_lock = threading.Lock()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: AuditEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, default=str) + "\n"
        with self._write_lock, self._file_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _read_all(self) -> list[AuditEvent]:
        if not self._file_path.exists():
            return []
        events: list[AuditEvent] = []
        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(AuditEvent.from_dict(json.loads(line)))
        return events

    def get(self, event_id: str) -> AuditEvent | None:
        for e in self._read_all():
            if e.event_id == event_id:
                return e
        return None

    def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        results: list[AuditEvent] = []
        for e in self._read_all():
            if event_type is not None and e.event_type != event_type:
                continue
            if actor is not None and e.actor != actor:
                continue
            if from_time is not None and e.timestamp < from_time:
                continue
            if to_time is not None and e.timestamp > to_time:
                continue
            results.append(e)
            if len(results) >= limit:
                break
        return results

    def count(self, event_type: str | None = None) -> int:
        events = self._read_all()
        if event_type is not None:
            return sum(1 for e in events if e.event_type == event_type)
        return len(events)

    def clear(self) -> None:
        with self._write_lock:
            if self._file_path.exists():
                self._file_path.unlink()


# ---------------------------------------------------------------------------
# AuditLogger facade
# ---------------------------------------------------------------------------

class AuditLogger:
    """High-level audit logging facade.

    Creates AuditEvent instances with auto-filled timestamp and correlation ID,
    appends them to the configured store, and emits a structured log line.
    """

    def __init__(self, store: AuditStore | None = None) -> None:
        self._store: AuditStore = store or MemoryAuditStore()

    @property
    def store(self) -> AuditStore:
        return self._store

    def log(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Create, persist, and log an audit event.

        Returns the created AuditEvent for inspection or forwarding.
        """
        from infrastructure.correlation import get_current_correlation_id

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            correlation_id=get_current_correlation_id() or "",
            ip_address=ip_address,
        )

        self._store.append(event)

        logger.info(
            "audit.%s",
            event_type,
            extra=event.to_dict(),
        )

        return event


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

audit_logger = AuditLogger()
