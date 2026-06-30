# Backward compat — moved to infrastructure.observability.tracing
from infrastructure.observability.tracing import (
    TraceContext,
    trace_event_handler,
    trace_operation,
)

__all__ = [
    "TraceContext",
    "trace_event_handler",
    "trace_operation",
]
