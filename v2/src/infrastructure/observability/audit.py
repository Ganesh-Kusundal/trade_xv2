"""Append-only audit sink (ponytail: in-memory list; swap for durable store later)."""

from __future__ import annotations

from typing import Any


class AuditSink:
    """Compliance audit log — append only; no delete/mutate of prior records."""

    def __init__(self) -> None:
        self._records: list[Any] = []

    def record(self, event: Any) -> None:
        self._records.append(event)

    @property
    def records(self) -> list[Any]:
        return list(self._records)
