"""Clock port — time abstraction for domain services."""

from typing import Protocol, runtime_checkable
from datetime import datetime


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
