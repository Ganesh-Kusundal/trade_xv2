"""Performance benchmarks for critical paths — latency and throughput."""

import time
from decimal import Decimal

import pytest

from brokers.common.core.domain import OrderResponse, OrderStatus, Position
from brokers.common.observability.metrics import MetricsCollector


@pytest.mark.performance
class TestOrderPlacementLatency:
    """Benchmark order placement path through the mapper and domain layers."""

    def test_domain_order_response_creation_latency(self):
        iterations = 10_000
        start = time.perf_counter()
        for i in range(iterations):
            OrderResponse.ok(f"ORD-{i}", "Success")
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 50, f"OrderResponse.ok() too slow: {per_op_us:.1f}μs/op"

    def test_domain_position_creation_latency(self):
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=100,
                avg_price=Decimal("2500"),
                ltp=Decimal("2550"),
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 50, f"Position() too slow: {per_op_us:.1f}μs/op"

    def test_order_status_normalize_latency(self):
        iterations = 10_000
        statuses = ["EXECUTED", "COMPLETE", "TRANSIT", "PARTIALLY_EXECUTED", "OPEN"]
        start = time.perf_counter()
        for i in range(iterations):
            OrderStatus.normalize(statuses[i % len(statuses)])
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 20, f"OrderStatus.normalize() too slow: {per_op_us:.1f}μs/op"


@pytest.mark.performance
class TestMapperThroughput:
    """Benchmark model mapping throughput."""

    def test_order_mapping_throughput(self):
        from brokers.common.core import models
        from brokers.common.core.enums import (
            ExchangeSegment,
            OrderStatus,
            OrderType,
            ProductType,
            TransactionType,
            Validity,
        )
        from brokers.common.core.mappers import order_to_domain

        model = models.Order(
            order_id="PERF-1",
            symbol="RELIANCE",
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=TransactionType.BUY,
            quantity=100,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
            validity=Validity.DAY,
            status=OrderStatus.OPEN,
        )

        iterations = 5_000
        start = time.perf_counter()
        for _ in range(iterations):
            order_to_domain(model)
        elapsed_ms = (time.perf_counter() - start) * 1000
        ops_per_sec = iterations / (elapsed_ms / 1000)
        assert ops_per_sec > 50_000, f"order_to_domain throughput too low: {ops_per_sec:.0f} ops/s"


@pytest.mark.performance
class TestMetricsCollectorOverhead:
    """Ensure metrics collection adds minimal overhead."""

    def test_metrics_recording_overhead(self):
        collector = MetricsCollector()
        iterations = 10_000

        start = time.perf_counter()
        for _i in range(iterations):
            collector.time_operation("bench_op", lambda: 42)
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_us = (elapsed_ms / iterations) * 1000
        assert per_op_us < 100, f"Metrics overhead too high: {per_op_us:.1f}μs/op"

        summary = collector.get_summary()
        assert summary["total_count"] == iterations
        assert summary["success_count"] == iterations
