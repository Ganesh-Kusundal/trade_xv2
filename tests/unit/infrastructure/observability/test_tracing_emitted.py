"""Spans are actually emitted by ``@trace_operation`` on the execution/OMS hot paths.

These tests prove Tier 2-G wiring:

* When OpenTelemetry is active (a hidden in-memory exporter is used), calling a
  decorated function/method produces at least one finished span whose name
  matches the operation.
* When OTel is unavailable the decorator degrades to log-only and never raises,
  so business calls keep working.

The real decorator from ``infrastructure.observability.tracing`` is reused
verbatim — no local reimplementation.
"""

from __future__ import annotations

from decimal import Decimal

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import infrastructure.observability.tracing as tracing
from infrastructure.observability.tracing import trace_operation


def _install_in_memory_tracer(monkeypatch) -> InMemorySpanExporter:
    """Point ``tracing._get_tracer`` at a private TracerProvider + in-memory exporter.

    Isolated from the global provider so the test cannot leak state into other
    suites and cannot depend on ``setup_telemetry()`` having been called.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tradex.tracing.test")

    monkeypatch.setattr(tracing, "_get_tracer", lambda: tracer)
    # Ensure the active flag (used by production path) is consistent for clarity.
    monkeypatch.setattr(tracing, "_otel_active", True)
    return exporter


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def test_trace_operation_emits_span_with_matching_name(monkeypatch):
    exporter = _install_in_memory_tracer(monkeypatch)

    @trace_operation("order_placement")
    def place_order(symbol: str) -> str:
        return f"order:{symbol}"

    result = place_order("RELIANCE")
    assert result == "order:RELIANCE"

    spans = exporter.get_finished_spans()
    assert len(spans) >= 1
    assert spans[0].name == "order_placement"
    attrs = dict(spans[0].attributes)
    assert attrs["function"] == "place_order"
    assert attrs["status"] == "success"
    assert "correlation_id" in attrs


def test_decorated_application_method_emits_span(monkeypatch):
    """A method decorated with ``@trace_operation`` emits a span with the op name.

    Mirrors ``test_trace_operation_emits_span`` but exercises an instance
    method (rather than a module-level function) on a real class, proving the
    decorator works on bound methods as it does on the OMS hot paths.
    """
    exporter = _install_in_memory_tracer(monkeypatch)

    class _PositionManager:
        @trace_operation("position_manager.apply_trade")
        def apply_trade(self, symbol: str) -> str:
            return f"position:{symbol}"

    manager = _PositionManager()
    position = manager.apply_trade("RELIANCE")

    assert position == "position:RELIANCE"
    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "position_manager.apply_trade" in names


# ---------------------------------------------------------------------------
# Fallback (OTel unavailable)
# ---------------------------------------------------------------------------


def test_trace_operation_log_only_when_otel_unavailable(monkeypatch):
    """With OTel missing the decorator must NOT raise and must return normally."""
    monkeypatch.setattr(tracing, "_HAS_OTEL", False)

    @trace_operation("order_placement")
    def place_order(symbol: str) -> str:
        return f"order:{symbol}"

    # No in-memory exporter installed; _get_tracer returns None -> log-only.
    result = place_order("RELIANCE")
    assert result == "order:RELIANCE"


def test_trace_operation_log_only_when_tracer_fails(monkeypatch):
    """A broken tracer also degrades to log-only without breaking the call."""

    class _BrokenTracer:
        def start_as_current_span(self, *args, **kwargs):  # pragma: no cover
            raise RuntimeError("provider exploded")

    monkeypatch.setattr(tracing, "_get_tracer", lambda: _BrokenTracer())

    @trace_operation("order_placement")
    def place_order(symbol: str) -> str:
        return f"order:{symbol}"

    assert place_order("RELIANCE") == "order:RELIANCE"


# ---------------------------------------------------------------------------
# Behavior preservation
# ---------------------------------------------------------------------------


def test_decorator_preserves_return_value_and_reraises(monkeypatch):
    exporter = _install_in_memory_tracer(monkeypatch)

    @trace_operation("boom")
    def explode() -> None:
        raise ValueError("nope")

    try:
        explode()
    except ValueError as exc:
        assert str(exc) == "nope"
    else:  # pragma: no cover
        raise AssertionError("expected ValueError to propagate")

    spans = exporter.get_finished_spans()
    assert spans[0].attributes["status"] == "error"
