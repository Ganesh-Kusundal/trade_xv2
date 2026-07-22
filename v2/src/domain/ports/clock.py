"""Clock protocol — time source abstraction."""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol, runtime_checkable

from domain.value_objects import Timestamp


@runtime_checkable
class Clock(Protocol):
    def now(self) -> Timestamp: ...
    def advance(self, delta: timedelta) -> None: ...
