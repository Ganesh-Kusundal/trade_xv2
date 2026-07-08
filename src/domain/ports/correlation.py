"""Correlation port — application-layer boundary for correlation ID management."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CorrelationProviderPort(Protocol):
    """Protocol for reading and writing the current correlation ID."""

    def get_current(self) -> str | None: ...

    def set_current(self, cid: str | None) -> None: ...
