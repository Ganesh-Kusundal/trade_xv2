"""Persistent append-only event log for crash recovery.

Every ORDER_UPDATED, TRADE, POSITION_UPDATE and other critical domain event
can be appended to a daily JSONL file. On startup the OMS can replay the log
to rebuild order/position state up to the point of the crash.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from brokers.common.event_bus import DomainEvent

logger = logging.getLogger(__name__)

DEFAULT_EVENTS_DIR = Path("market_data/events")


# Domain types that may appear in event payloads and can be round-tripped.
_DOMAIN_TYPES: dict[str, type] = {}


def _register_domain_type(cls: type) -> type:
    key = f"{cls.__module__}.{cls.__qualname__}"
    _DOMAIN_TYPES[key] = cls
    return cls


def _serialize_value(value: Any) -> Any:
    """Best-effort serialization of domain objects and primitives."""
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if dataclasses.is_dataclass(value):
        cls = type(value)
        key = f"{cls.__module__}.{cls.__qualname__}"
        _register_domain_type(cls)
        result: dict[str, Any] = {"__type__": key}
        for field in dataclasses.fields(value):
            result[field.name] = _serialize_value(getattr(value, field.name))
        return result
    if isinstance(value, list | tuple):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return str(value)


def _deserialize_value(value: Any, expected_type: type | None = None) -> Any:
    """Reconstruct domain objects serialized by ``_serialize_value``."""
    import enum
    import typing

    if expected_type is not None:
        origin = typing.get_origin(expected_type)
        if origin is not None:
            expected_type = origin
        if isinstance(expected_type, type) and issubclass(expected_type, enum.Enum):
            try:
                return expected_type(value)
            except Exception:
                pass

    if isinstance(value, dict):
        if "__type__" in value:
            t = value["__type__"]
            if t == "decimal":
                return Decimal(value["value"])
            if t == "datetime":
                return datetime.fromisoformat(value["value"])
            if t == "date":
                return date.fromisoformat(value["value"])
            cls = _DOMAIN_TYPES.get(t)
            if cls is not None and dataclasses.is_dataclass(cls):
                try:
                    type_hints = typing.get_type_hints(cls)
                except Exception:
                    type_hints = {}
                kwargs = {
                    f.name: _deserialize_value(
                        value.get(f.name), type_hints.get(f.name)
                    )
                    for f in dataclasses.fields(cls)
                    if f.init
                }
                return cls(**kwargs)
        return {k: _deserialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize_value(v) for v in value]
    return value


def _deserialize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Deserialize a payload dict, reconstructing any embedded domain objects."""
    return {k: _deserialize_value(v) for k, v in payload.items()}


class EventLog:
    """Append-only JSONL event log with day-based rotation.

    Thread-safe. Writes are line-buffered and fsynced so a crash loses at most
    the last event. Reads replay events in insertion order.

    Append failures are **never silent**: every failure is logged at ERROR
    level and recorded in :attr:`append_errors` so operators can alert on it.
    """

    def __init__(self, events_dir: str | Path | None = None) -> None:
        self._events_dir = Path(events_dir) if events_dir else DEFAULT_EVENTS_DIR
        self._events_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._current_file: Path | None = None
        self._current_handle: Any = None
        self.append_errors: int = 0  # public counter, never reset mid-run

    @property
    def errors(self) -> int:
        """Number of append errors since process start."""
        return self.append_errors

    def _file_for(self, dt: datetime) -> Path:
        return self._events_dir / f"{dt.date().isoformat()}.jsonl"

    def _ensure_handle(self, dt: datetime) -> Any:
        target = self._file_for(dt)
        if self._current_file != target:
            if self._current_handle is not None:
                try:
                    self._current_handle.flush()
                    self._current_handle.close()
                except Exception as exc:
                    logger.warning("Error closing old event log: %s", exc)
            self._current_handle = open(target, "a", encoding="utf-8")
            self._current_file = target
        return self._current_handle

    def append(self, event: DomainEvent) -> None:
        """Append a single event to the current day's log.

        Raises
        ------
        OSError
            If the log file cannot be written. The exception is **not**
            swallowed — the bus will catch it, log it, and dead-letter the
            event. Callers that need to swallow failures (none in
            production) must do so explicitly.
        """
        record = {
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "symbol": event.symbol,
            "payload": self._serialize_payload(event.payload),
        }
        line = json.dumps(record, separators=(",", ":"), default=str)
        with self._lock:
            handle = self._ensure_handle(event.timestamp)
            try:
                handle.write(line + "\n")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except (OSError, ValueError):
                    # Some filesystems don't support fsync. The flush above
                    # is the best we can do.
                    pass
            except (OSError, ValueError) as exc:
                self.append_errors += 1
                logger.error(
                    "EventLog: failed to append %s to %s: %s",
                    event.event_type,
                    self._current_file,
                    exc,
                    exc_info=True,
                )
                # Re-raise so the EventBus can dead-letter the event.
                raise

    def _serialize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Best-effort serialization of domain objects in the payload."""
        return {k: _serialize_value(v) for k, v in payload.items()}

    def replay(
        self,
        since: datetime | None = None,
        event_types: set[str] | None = None,
        handler: Callable[[DomainEvent], None] | None = None,
    ) -> list[DomainEvent]:
        """Replay events from the log.

        Args:
            since: Only replay events at or after this time. If None, replay all.
            event_types: If provided, only replay these event types.
            handler: Optional callback invoked for each replayed event.

        Returns:
            List of replayed DomainEvent objects.
        """
        events: list[DomainEvent] = []
        files = sorted(self._events_dir.glob("*.jsonl"))
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    # Read all lines up front so newly appended events during
                    # replay are not recursively processed.
                    lines = [line.strip() for line in f if line.strip()]
            except Exception as exc:
                logger.warning("Failed to read event log %s: %s", path, exc)
                continue
            for line in lines:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = datetime.fromisoformat(record["timestamp"])
                if since is not None and ts < since:
                    continue
                etype = record.get("event_type", "")
                if event_types is not None and etype not in event_types:
                    continue
                event = DomainEvent(
                    event_type=etype,
                    timestamp=ts,
                    payload=_deserialize_payload(record.get("payload", {})),
                    symbol=record.get("symbol"),
                    source=record.get("source", ""),
                )
                events.append(event)
                if handler is not None:
                    handler(event)
        return events

    def close(self) -> None:
        """Close the current log handle."""
        with self._lock:
            if self._current_handle is not None:
                try:
                    self._current_handle.flush()
                    self._current_handle.close()
                except Exception as exc:
                    logger.warning("Error closing event log: %s", exc)
                self._current_handle = None
                self._current_file = None

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
