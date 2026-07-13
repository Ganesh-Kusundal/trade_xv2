"""Audit emit port — application calls these; infrastructure wires the sink.

Composition root should call :func:`set_audit_sink` with the infrastructure
implementations (or leave unset for no-op / tests).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuditSink:
    """Callables for cross-cutting audit events (all optional / best-effort)."""

    emit_routing_decision: Callable[[Any], None] | None = None
    emit_quota_event: Callable[..., None] | None = None
    emit_historical_chunk: Callable[..., None] | None = None
    emit_merge_conflict: Callable[..., None] | None = None
    emit_stream_state_change: Callable[..., None] | None = None


_sink = AuditSink()


def set_audit_sink(sink: AuditSink) -> None:
    """Register audit emitters (composition root)."""
    global _sink
    _sink = sink


def emit_routing_decision(decision: Any) -> None:
    fn = _sink.emit_routing_decision
    if fn is not None:
        fn(decision)


def emit_quota_event(*args: Any, **kwargs: Any) -> None:
    fn = _sink.emit_quota_event
    if fn is not None:
        fn(*args, **kwargs)


def emit_historical_chunk(*args: Any, **kwargs: Any) -> None:
    fn = _sink.emit_historical_chunk
    if fn is not None:
        fn(*args, **kwargs)


def emit_merge_conflict(*args: Any, **kwargs: Any) -> None:
    fn = _sink.emit_merge_conflict
    if fn is not None:
        fn(*args, **kwargs)


def emit_stream_state_change(*args: Any, **kwargs: Any) -> None:
    fn = _sink.emit_stream_state_change
    if fn is not None:
        fn(*args, **kwargs)
