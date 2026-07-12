"""Execution hot-path methods emit spans via @trace_operation (Tier 2-G).

Uses the existing ``FakeOrderManager`` so the execution use-case wiring is
exercised end-to-end without a broker. Spans are captured by a hidden
in-memory OTel exporter pointed at via ``tracing._get_tracer``.
"""

from __future__ import annotations

from decimal import Decimal

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import infrastructure.observability.tracing as tracing
from application.execution.cancel_order_use_case import CancelOrderUseCase
from application.execution.place_order_use_case import PlaceOrderUseCase
from domain.orders.requests import OrderRequest
from tests.fakes.fake_oms import FakeOrderManager


class _CancelFnAwareFakeManager(FakeOrderManager):
    """FakeOrderManager honors the IOrderManager.cancel_order cancel_fn kwarg."""

    def cancel_order(self, order_id: str, *, cancel_fn=None) -> object:  # type: ignore[override]
        return super().cancel_order(order_id)


def _install_in_memory_tracer(monkeypatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("tradex.tracing.test")
    monkeypatch.setattr(tracing, "_get_tracer", lambda: tracer)
    monkeypatch.setattr(tracing, "_otel_active", True)
    # Patch the no-op trace_operation in the application layer, then reload
    # so the @trace_operation decorators on use-case classes rebind to the real tracer.
    import importlib
    import application.observability as app_obs
    monkeypatch.setattr(app_obs, "trace_operation", tracing.trace_operation)
    importlib.reload(importlib.import_module("application.execution.place_order_use_case"))
    importlib.reload(importlib.import_module("application.execution.cancel_order_use_case"))
    return exporter


def _request() -> OrderRequest:
    return OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        order_type="MARKET",
        quantity=10,
        product_type="INTRADAY",
        correlation_id="test-tracing-001",
    )


def test_place_order_use_case_emits_span(monkeypatch):
    exporter = _install_in_memory_tracer(monkeypatch)
    # Import AFTER patching so the reloaded module's classes are used
    from application.execution.place_order_use_case import PlaceOrderUseCase
    from tests.fakes.fake_oms import FakeOrderManager

    class _CancelFnAwareFakeManager(FakeOrderManager):
        def cancel_order(self, order_id: str, *, cancel_fn=None) -> object:
            return super().cancel_order(order_id)

    fake = _CancelFnAwareFakeManager()
    result = PlaceOrderUseCase(fake).execute(_request())

    assert result.success
    assert len(fake.orders_placed) == 1
    names = [s.name for s in exporter.get_finished_spans()]
    assert "place_order" in names


def test_cancel_order_use_case_emits_span(monkeypatch):
    exporter = _install_in_memory_tracer(monkeypatch)
    from application.execution.place_order_use_case import PlaceOrderUseCase
    from application.execution.cancel_order_use_case import CancelOrderUseCase
    from tests.fakes.fake_oms import FakeOrderManager

    class _CancelFnAwareFakeManager(FakeOrderManager):
        def cancel_order(self, order_id: str, *, cancel_fn=None) -> object:
            return super().cancel_order(order_id)

    fake = _CancelFnAwareFakeManager()
    PlaceOrderUseCase(fake).execute(_request())

    result = CancelOrderUseCase(fake).execute(fake.orders_placed[0].order_id)

    assert result.success
    names = [s.name for s in exporter.get_finished_spans()]
    assert "cancel_order" in names
