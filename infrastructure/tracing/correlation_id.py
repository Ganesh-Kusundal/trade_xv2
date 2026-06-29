"""
CORRELATION ID MANAGER
Propagates unique trace IDs across API → OMS → Broker → Fill → DB.
Enables debugging of complex async flows in production.
"""
import uuid
from contextvars import ContextVar
from typing import Optional

# Thread-safe context variable for current trace ID
_current_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_current_span_id: ContextVar[Optional[str]] = ContextVar('span_id', default=None)

class TraceContext:
    """Manages distributed tracing context for a single request lifecycle."""
    
    @staticmethod
    def start_trace(operation: str) -> str:
        """Start a new trace for an incoming request (e.g., API call, Signal)."""
        trace_id = str(uuid.uuid4())
        span_id = f"{operation}.{uuid.uuid4().hex[:8]}"
        _current_trace_id.set(trace_id)
        _current_span_id.set(span_id)
        return trace_id
    
    @staticmethod
    def get_trace_id() -> Optional[str]:
        """Get current trace ID (propagated from parent)."""
        return _current_trace_id.get()
    
    @staticmethod
    def get_span_id() -> Optional[str]:
        """Get current span ID."""
        return _current_span_id.get()
    
    @staticmethod
    def create_child_span(operation: str) -> str:
        """Create a child span for a sub-operation (e.g., DB call, Broker API)."""
        parent_trace = _current_trace_id.get()
        if not parent_trace:
            return TraceContext.start_trace(operation)
        
        span_id = f"{parent_trace}.{operation}.{uuid.uuid4().hex[:8]}"
        _current_span_id.set(span_id)
        return span_id
    
    @staticmethod
    def inject_headers(headers: dict) -> dict:
        """Inject trace IDs into outgoing HTTP/WebSocket headers."""
        trace_id = _current_trace_id.get()
        span_id = _current_span_id.get()
        if trace_id:
            headers['X-Trace-ID'] = trace_id
        if span_id:
            headers['X-Span-ID'] = span_id
        return headers
    
    @staticmethod
    def extract_headers(headers: dict) -> Optional[str]:
        """Extract trace IDs from incoming headers."""
        trace_id = headers.get('X-Trace-ID')
        if trace_id:
            _current_trace_id.set(trace_id)
            _current_span_id.set(headers.get('X-Span-ID', f"root.{uuid.uuid4().hex[:8]}"))
        return trace_id
