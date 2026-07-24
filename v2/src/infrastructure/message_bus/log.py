"""MessageLog protocol and implementations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable


def _json_serializer(obj: Any) -> Any:
    """JSON serializer that handles datetime and other common types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


@runtime_checkable
class MessageLog(Protocol):
    """Protocol for message logging and replay."""

    def append(self, message: object) -> None: ...
    def read(self, start: datetime | None = None, end: datetime | None = None) -> Iterator[object]: ...
    def read_session(self, session_id: str) -> Iterator[object]: ...
    def clear(self) -> None: ...


class InMemoryMessageLog:
    """In-memory message log implementation."""

    def __init__(self) -> None:
        self._messages: list[object] = []

    def append(self, message: object) -> None:
        self._messages.append(message)

    def read(self, start: datetime | None = None, end: datetime | None = None) -> Iterator[object]:
        for msg in self._messages:
            if start is not None or end is not None:
                ts = getattr(msg, "timestamp", None)
                if ts is not None:
                    if start is not None and ts < start:
                        continue
                    if end is not None and ts > end:
                        continue
            yield msg

    def read_session(self, session_id: str) -> Iterator[object]:
        for msg in self._messages:
            msg_session = getattr(msg, "session_id", None)
            if msg_session == session_id:
                yield msg

    def clear(self) -> None:
        self._messages.clear()


class SQLiteMessageLog:
    """SQLite-backed message log for durable event persistence."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    message_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                ON messages(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id)
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _serialize(self, message: object) -> str:
        return json.dumps({
            "type": type(message).__name__,
            "data": message.__dict__ if hasattr(message, "__dict__") else str(message),
        }, default=_json_serializer)

    def _deserialize(self, row: sqlite3.Row) -> object:
        data = json.loads(row["payload"])
        cls_name = data["type"]
        # Try to find the class in common message types
        try:
            cls = globals().get(cls_name) or getattr(__import__("domain.events", fromlist=[cls_name]), cls_name, None)
        except ImportError:
            cls = None
        if cls is None:
            class DynamicMessage:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            return DynamicMessage(**data["data"])
        return cls(**data["data"])

    def append(self, message: object) -> None:
        timestamp = getattr(message, "timestamp", datetime.now(UTC))
        if isinstance(timestamp, datetime):
            ts_str = timestamp.isoformat()
        else:
            ts_str = str(timestamp)
        session_id = getattr(message, "session_id", None)
        message_type = type(message).__name__
        payload = self._serialize(message)

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (timestamp, session_id, message_type, payload) VALUES (?, ?, ?, ?)",
                (ts_str, session_id, message_type, payload),
            )

    def read(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> Iterator[object]:
        query = "SELECT * FROM messages WHERE 1=1"
        params: list = []

        if start is not None:
            query += " AND timestamp >= ?"
            params.append(start.isoformat())
        if end is not None:
            query += " AND timestamp <= ?"
            params.append(end.isoformat())

        query += " ORDER BY timestamp ASC"

        with self._connect() as conn:
            for row in conn.execute(query, params):
                yield self._deserialize(row)

    def read_session(self, session_id: str) -> Iterator[object]:
        with self._connect() as conn:
            for row in conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ):
                yield self._deserialize(row)

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages")
