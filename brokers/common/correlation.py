"""Correlation ID framework for distributed tracing across broker operations.

Provides utilities to generate, propagate, and inspect correlation IDs
that flow through the system — from CLI commands → gateway → event bus →
datalake. Every ``DomainEvent``, ``Trade``, ``Position``, and ``Holding``
can carry a ``correlation_id`` string for end-to-end traceability.

Usage::

    from brokers.common.correlation import generate_correlation_id, with_correlation

    # Automatic generation
    cid = generate_correlation_id()

    # Context manager for scoped tracing
    with with_correlation(cid):
        gateway.place_order(..., correlation_id=cid)
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from datetime import datetime, timezone
from typing import Generator


# Thread-local storage for implicit correlation ID propagation.
_correlation_local = threading.local()


def generate_correlation_id() -> str:
    """Generate a unique correlation ID.

    Format: ``{timestamp_ms}-{uuid_short}``

    Example: ``1718601234567-a1b2c3d4e5f6``
    """
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
    """Context manager that sets a correlation ID for the duration of the block.

    If *cid* is ``None``, a new ID is auto-generated.

    Usage::

        with with_correlation() as cid:
            do_work()
    """
    if cid is None:
        cid = generate_correlation_id()
    previous = get_current_correlation_id()
    set_current_correlation_id(cid)
    try:
        yield cid
    finally:
        set_current_correlation_id(previous)
