"""Runtime clock — stdlib UTC time (no infrastructure dependency).

Keeps ``tradex.runtime`` free of ``infrastructure`` imports so application
code can use the kernel without violating hexagonal layering.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


class Clock:
    """Minimal time source used by router / provenance / streams."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return time.time()


time_service = Clock()
