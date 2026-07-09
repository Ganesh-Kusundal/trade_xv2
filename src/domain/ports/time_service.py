"""Time service port — application-layer boundary for time operations."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class TimeServicePort(Protocol):
    """Protocol for time-related operations used by broker code."""

    def now(self) -> datetime: ...

    def timestamp(self) -> float: ...
