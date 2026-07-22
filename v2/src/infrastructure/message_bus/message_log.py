"""In-memory message log for append-before-dispatch replay support."""

from __future__ import annotations

from datetime import datetime
from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class MessageLog(Protocol):
    def append(self, message: object) -> None: ...

    def read(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[object]: ...

    def clear(self) -> None: ...


class InMemoryMessageLog:
    """Simple list-backed log. Messages may carry an optional ``timestamp`` attr."""

    def __init__(self) -> None:
        self._messages: list[object] = []

    def append(self, message: object) -> None:
        self._messages.append(message)

    def read(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[object]:
        for msg in self._messages:
            ts = getattr(msg, "timestamp", None)
            if start is not None and ts is not None and ts < start:
                continue
            if end is not None and ts is not None and ts > end:
                continue
            yield msg

    def clear(self) -> None:
        self._messages.clear()
