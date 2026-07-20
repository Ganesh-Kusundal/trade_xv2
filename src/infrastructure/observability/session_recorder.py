"""SessionRecorder — optional, non-critical durable capture of a live session.

Fills the one real gap identified when auditing the three Replay concepts
this platform's blueprint requires be kept distinct (ResearchReplay,
SessionRecording, CrashRecovery — see
docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART3.md §4):
ResearchReplay and CrashRecovery both already exist; SessionRecording did
not exist at all (confirmed via a clean zero-match grep before this file
was added).

Deliberately small and deliberately non-critical:

* Exactly one subscription — the same EventHub fan-out edge Observability
  already uses (see Part 1 §6: "fire-and-forget... losing an event costs
  visibility, not money").
* Zero consumers on any live decision path. Nothing in Trading, Risk, or
  the OMS reads this file back. Losing it, corrupting it, or disabling it
  changes no live behavior — that is the whole point, and the reason it is
  safe to build this cheaply.
* Every write is wrapped so a recording failure (disk full, permissions,
  serialization error) is logged and swallowed, never raised into the
  event-publishing call path it observes.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.events.types import DomainEvent
    from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)


def _default_session_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "runtime" / "session-recordings"


class SessionRecorder:
    """Subscribes to every event type on an EventBus and appends each one,
    as a JSON line, to a per-session file — for later offline analysis
    only.

    Usage::

        recorder = SessionRecorder(event_bus, session_id="live-2026-07-10")
        recorder.start()
        ...
        recorder.stop()
    """

    def __init__(
        self,
        event_bus: EventBus,
        session_id: str | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._session_id = session_id or uuid.uuid4().hex[:12]
        self._dir = (output_dir or _default_session_dir()).resolve()
        self._path = self._dir / f"{self._session_id}.jsonl"
        self._tokens: list[str] = []
        self._lock = threading.Lock()
        self._events_written = 0
        self._write_failures = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def events_written(self) -> int:
        return self._events_written

    @property
    def write_failures(self) -> int:
        """Count of failed writes — visibility only, never raised."""
        return self._write_failures

    def start(self) -> None:
        """Begin capturing. Idempotent — calling twice while already
        started is a no-op (does not double-subscribe)."""
        if self._tokens:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        self._tokens = self._event_bus.subscribe_all(self._on_event)
        logger.info(
            "session_recorder_started",
            extra={"session_id": self._session_id, "path": str(self._path)},
        )

    def stop(self) -> None:
        """Stop capturing and unsubscribe. Safe to call multiple times."""
        for token in self._tokens:
            try:
                self._event_bus.unsubscribe(token)
            except Exception:
                logger.warning("session_recorder_unsubscribe_failed", exc_info=True)
        self._tokens = []
        logger.info(
            "session_recorder_stopped",
            extra={
                "session_id": self._session_id,
                "events_written": self._events_written,
                "write_failures": self._write_failures,
            },
        )

    def _on_event(self, event: DomainEvent) -> None:
        """Fire-and-forget capture. Never let a recording failure surface
        to the caller publishing the event."""
        try:
            line = self._serialize(event)
        except Exception:
            self._write_failures += 1
            logger.warning("session_recorder_serialize_failed", exc_info=True)
            return
        try:
            with self._lock:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.write("\n")
                self._events_written += 1
        except Exception:
            self._write_failures += 1
            logger.warning("session_recorder_write_failed", exc_info=True)

    @staticmethod
    def _serialize(event: DomainEvent) -> str:
        # Deliberately NOT dataclasses.asdict(): it recursively deep-copies
        # every field, and DomainEvent.payload is a MappingProxyType
        # (shallow-frozen in __post_init__) -- mappingproxy cannot be
        # deep-copied/pickled, so asdict() crashes before this method gets
        # a chance to convert it. A shallow, manual field extraction avoids
        # the deep-copy entirely.
        if is_dataclass(event):
            data: dict[str, Any] = {f.name: getattr(event, f.name) for f in dataclass_fields(event)}
        else:
            data = dict(vars(event))
        # DomainEvent.timestamp is a tz-aware datetime; payload may contain
        # a MappingProxyType (shallow-frozen) — both need plain-JSON forms.
        ts = data.get("timestamp")
        if isinstance(ts, datetime):
            data["timestamp"] = ts.astimezone(timezone.utc).isoformat()
        payload = data.get("payload")
        if payload is not None and not isinstance(payload, dict):
            data["payload"] = dict(payload)
        return json.dumps(data, default=str)


__all__ = ["SessionRecorder"]
