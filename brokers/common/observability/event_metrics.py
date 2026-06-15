"""In-process event metrics for the OMS / event bus.

This is intentionally tiny and dependency-free: a production deployment
should replace it with a Prometheus / OpenTelemetry exporter, but the
shape (counters and a snapshot method) stays the same so swapping is
trivial.

The metrics here are **never** swallowed. Every increment is observable
via :func:`snapshot`, which is what the alerting layer polls.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any


class EventMetrics:
    """Thread-safe counter store keyed by ``(event_type, outcome)``.

    Outcomes used by the bus:

    - ``published`` — event was accepted by the bus.
    - ``dispatched`` — handler invocation started.
    - ``handler_ok`` — handler returned without raising.
    - ``handler_error`` — handler raised (counted per (event_type, error_type)).
    - ``dead_letter`` — handler failures sent to the dead-letter queue.
    - ``log_error`` — persistent log append failed (counted per error type).
    - ``duplicated_trade`` — a trade that was already processed (idempotency hit).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, str], int] = defaultdict(int)

    def inc(self, event_type: str, outcome: str, by: int = 1) -> None:
        if by <= 0:
            return
        with self._lock:
            self._counters[(event_type, outcome)] += by

    def get(self, event_type: str, outcome: str) -> int:
        with self._lock:
            return self._counters.get((event_type, outcome), 0)

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Return a JSON-serializable view of every counter."""
        with self._lock:
            out: dict[str, dict[str, int]] = defaultdict(dict)
            for (event_type, outcome), value in self._counters.items():
                out[event_type][outcome] = value
            return dict(out)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()

    def render(self) -> str:
        """Human-readable rendering, mostly for the CLI / logs."""
        lines = ["event_type | outcome | count"]
        for (event_type, outcome), value in sorted(self._counters.items()):
            lines.append(f"{event_type} | {outcome} | {value}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {"events": self.snapshot()}
