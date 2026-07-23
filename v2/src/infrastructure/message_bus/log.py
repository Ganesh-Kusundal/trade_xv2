"""MessageLog protocol and in-memory implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Iterator, Protocol, runtime_checkable


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
