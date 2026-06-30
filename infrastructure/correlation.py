"""Correlation ID framework for distributed tracing.

ContextVar-based correlation ID propagation used by the event bus,
gateways, and OMS. Lives in infrastructure (no broker or domain imports).

Uses ``contextvars.ContextVar`` instead of ``threading.local()`` so
correlation IDs propagate correctly across async task boundaries.
"""

from __future__ import annotations

import contextlib
import contextvars
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

_correlation_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def generate_correlation_id() -> str:
    """Generate a unique correlation ID (``{timestamp_ms}-{uuid_short}``)."""
    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    short = uuid.uuid4().hex[:12]
    return f"{ts_ms}-{short}"


def get_current_correlation_id() -> str | None:
    """Return the correlation ID active on the current context, or ``None``."""
    return _correlation_var.get()


def set_current_correlation_id(cid: str | None) -> None:
    """Set the correlation ID for the current context."""
    _correlation_var.set(cid)


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
