"""Correlation ID framework for distributed tracing.

Thread-local correlation ID propagation used by the event bus, gateways,
and OMS. Lives in infrastructure (no broker or domain imports).
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from datetime import datetime, timezone
from typing import Generator

_correlation_local = threading.local()


def generate_correlation_id() -> str:
    """Generate a unique correlation ID (``{timestamp_ms}-{uuid_short}``)."""
    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    short = uuid.uuid4().hex[:12]
    return f"{ts_ms}-{short}"


def get_current_correlation_id() -> str | None:
    """Return the correlation ID active on the current thread, or ``None``."""
    return getattr(_correlation_local, "correlation_id", None)


def set_current_correlation_id(cid: str | None) -> None:
    """Set the correlation ID for the current thread."""
    _correlation_local.correlation_id = cid


@contextlib.contextmanager
def with_correlation(cid: str | None = None) -> Generator[str | None, None, None]:
    """Context manager that sets a correlation ID for the duration of the block."""
    if cid is None:
        cid = generate_correlation_id()
    previous = get_current_correlation_id()
    set_current_correlation_id(cid)
    try:
        yield cid
    finally:
        set_current_correlation_id(previous)
