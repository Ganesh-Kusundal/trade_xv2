"""Tests for metrics collection infrastructure (P5 Stability Engineering).

Verifies:
1. Counter metrics track monotonically increasing values
2. Gauge metrics track current values
3. Histogram metrics track distributions with statistics
4. Metrics are thread-safe
5. Convenience functions work for common trading metrics
"""

import threading

import pytest

from infrastructure.metrics import (
    CounterMetric,
    GaugeMetric,
    HistogramMetric,
    MetricLabels,
    MetricsCollector,
    get_metrics_collector,
    reset_metrics_collector,
    track_error,
    track_event_processing,
    track_order_cancellation,
    track_order_placement,
    track_trade_execution,
)


class TestMetricLabels:
    """Test metric labels functionality."""

    def test_labels_set_and_get(self):
        """Labels should store and retrieve values."""
        labels = MetricLabels()
        labels.set("broker", "dhan")
        labels.set("symbol", "RELIANCE")

        assert labels.get("broker") == "dhan"
        assert labels.get("symbol") == "RELIANCE"

    def test_labels_to_dict(self):
        """Labels should convert to dictionary."""
        labels = MetricLabels()
        labels.set("broker", "dhan")

        result = labels.to_dict()
        assert result == {"broker": "dhan"}

    def test_labels_hash_and_equality(self):
        """Labels with same values should be equal and have same hash."""
        labels1 = MetricLabels()
        labels1.set("broker", "dhan")

        labels2 = MetricLabels()
        labels2.set("broker", "dhan")

        assert labels1 == labels2
        assert hash(labels1) == hash(labels2)


class TestCounterMetric:
    """Test counter metric."""

    def test_counter_increment(self):
        """Counter should increment correctly."""
        counter = CounterMetric(name="test", labels=MetricLabels())
        counter.increment()
        counter.increment(5)

        assert counter.value == 6

    def test_counter_rejects_negative_increment(self):
        """Counter should reject negative increments."""
        counter = CounterMetric(name="test", labels=MetricLabels())

        with pytest.raises(ValueError, match="Counter can only be incremented"):
            counter.increment(-1)

    def test_counter_to_dict(self):
        """Counter should export to dictionary."""
        labels = MetricLabels()
        labels.set("broker", "dhan")

        counter = CounterMetric(name="orders.placed", labels=labels)
        counter.increment(10)

        result = counter.to_dict()
        assert result["name"] == "orders.placed"
        assert result["type"] == "counter"
        assert result["value"] == 10
        assert result["labels"] == {"broker": "dhan"}


class TestGaugeMetric:
    """Test gauge metric."""

    def test_gauge_set(self):
        """Gauge should set value correctly."""
        gauge = GaugeMetric(name="test", labels=MetricLabels())
        gauge.set(42.5)

        assert gauge.value == 42.5

    def test_gauge_increment_and_decrement(self):
        """Gauge should increment and decrement."""
        gauge = GaugeMetric(name="test", labels=MetricLabels())
        gauge.set(10)
        gauge.increment(5)
        gauge.decrement(3)

        assert gauge.value == 12.0

    def test_gauge_to_dict(self):
        """Gauge should export to dictionary."""
        gauge = GaugeMetric(name="positions.open", labels=MetricLabels())
        gauge.set(5)

        result = gauge.to_dict()
        assert result["name"] == "positions.open"
        assert result["type"] == "gauge"
        assert result["value"] == 5.0


class TestHistogramMetric:
    """Test histogram metric."""

    def test_histogram_observe(self):
        """Histogram should record observations."""
        histogram = HistogramMetric(name="test", labels=MetricLabels())
        histogram.observe(10.0)
        histogram.observe(20.0)
        histogram.observe(30.0)

        stats = histogram.get_statistics()
        assert stats["count"] == 3
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["avg"] == 20.0

    def test_histogram_percentiles(self):
        """Histogram should calculate percentiles correctly."""
        histogram = HistogramMetric(name="test", labels=MetricLabels())

        # Add 100 samples
        for i in range(1, 101):
            histogram.observe(float(i))

        stats = histogram.get_statistics()
        # Percentiles are approximate due to discrete sampling
        assert 49.0 <= stats["p50"] <= 51.0
        assert 94.0 <= stats["p95"] <= 96.0
        assert 98.0 <= stats["p99"] <= 100.0

    def test_histogram_empty_statistics(self):
        """Histogram should return zeros for empty samples."""
        histogram = HistogramMetric(name="test", labels=MetricLabels())

        stats = histogram.get_statistics()
        assert stats["count"] == 0
        assert stats["avg"] == 0.0

    def test_histogram_to_dict(self):
        """Histogram should export to dictionary with statistics."""
        histogram = HistogramMetric(name="latency", labels=MetricLabels())
        histogram.observe(100.0)

        result = histogram.to_dict()
        assert result["name"] == "latency"
        assert result["type"] == "histogram"
        assert result["count"] == 1


class TestMetricsCollector:
    """Test metrics collector."""

    def setup_method(self) -> None:
        """Reset collector before each test."""
        reset_metrics_collector()

    def test_increment_counter(self):
        """Collector should increment counters."""
        collector = MetricsCollector()
        collector.increment("orders.placed", labels={"broker": "dhan"})
        collector.increment("orders.placed", labels={"broker": "dhan"}, amount=5)

        snapshot = collector.get_snapshot()
        assert len(snapshot["counters"]) == 1
        assert snapshot["counters"][0]["value"] == 6

    def test_set_gauge(self):
        """Collector should set gauges."""
        collector = MetricsCollector()
        collector.set_gauge("positions.open", 5)

        snapshot = collector.get_snapshot()
        assert len(snapshot["gauges"]) == 1
        assert snapshot["gauges"][0]["value"] == 5.0

    def test_observe_histogram(self):
        """Collector should observe histogram values."""
        collector = MetricsCollector()
        collector.observe_histogram("latency", 100.0)
        collector.observe_histogram("latency", 200.0)

        snapshot = collector.get_snapshot()
        assert len(snapshot["histograms"]) == 1
        assert snapshot["histograms"][0]["count"] == 2

    def test_get_snapshot(self):
        """Collector should export snapshot with all metric types."""
        collector = MetricsCollector()
        collector.increment("counter1")
        collector.set_gauge("gauge1", 42.0)
        collector.observe_histogram("histogram1", 50.0)

        snapshot = collector.get_snapshot()
        assert "counters" in snapshot
        assert "gauges" in snapshot
        assert "histograms" in snapshot
        assert "timestamp" in snapshot

    def test_reset(self):
        """Collector should reset all metrics."""
        collector = MetricsCollector()
        collector.increment("counter1")
        collector.set_gauge("gauge1", 42.0)

        collector.reset()
        snapshot = collector.get_snapshot()

        assert len(snapshot["counters"]) == 0
        assert len(snapshot["gauges"]) == 0
        assert len(snapshot["histograms"]) == 0


class TestThreadSafety:
    """Test thread-safety of metrics collection."""

    def test_counter_thread_safety(self):
        """Counter increments should be thread-safe."""
        collector = MetricsCollector()

        def worker() -> None:
            for _ in range(1000):
                collector.increment("test.counter")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snapshot = collector.get_snapshot()
        assert snapshot["counters"][0]["value"] == 10000  # 10 threads * 1000 increments

    def test_histogram_thread_safety(self):
        """Histogram observations should be thread-safe."""
        collector = MetricsCollector()

        def worker() -> None:
            for i in range(100):
                collector.observe_histogram("test.histogram", float(i))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snapshot = collector.get_snapshot()
        assert snapshot["histograms"][0]["count"] == 1000  # 10 threads * 100 observations


class TestConvenienceFunctions:
    """Test convenience functions for common trading metrics."""

    def setup_method(self) -> None:
        """Reset collector before each test."""
        reset_metrics_collector()

    def test_track_order_placement(self):
        """track_order_placement should record metrics."""
        track_order_placement("dhan", 45.2)

        metrics = get_metrics_collector()
        snapshot = metrics.get_snapshot()

        assert len(snapshot["counters"]) == 1
        assert snapshot["counters"][0]["name"] == "orders.placed"
        assert len(snapshot["histograms"]) == 1
        assert snapshot["histograms"][0]["name"] == "order.latency_ms"

    def test_track_order_cancellation(self):
        """track_order_cancellation should record metrics."""
        track_order_cancellation("upstox", 30.1)

        metrics = get_metrics_collector()
        snapshot = metrics.get_snapshot()

        assert len(snapshot["counters"]) == 1
        assert snapshot["counters"][0]["name"] == "orders.cancelled"

    def test_track_trade_execution(self):
        """track_trade_execution should record metrics."""
        track_trade_execution("dhan", "RELIANCE", 50.5)

        metrics = get_metrics_collector()
        snapshot = metrics.get_snapshot()

        assert len(snapshot["counters"]) == 1
        assert snapshot["counters"][0]["name"] == "trades.executed"

    def test_track_error(self):
        """track_error should record error metrics."""
        track_error("order_manager", "ValidationError")

        metrics = get_metrics_collector()
        snapshot = metrics.get_snapshot()

        assert len(snapshot["counters"]) == 1
        assert snapshot["counters"][0]["name"] == "errors.total"

    def test_track_event_processing(self):
        """track_event_processing should record event metrics."""
        track_event_processing("ORDER_UPDATED", 25.3, success=True)

        metrics = get_metrics_collector()
        snapshot = metrics.get_snapshot()

        assert len(snapshot["counters"]) == 1
        assert snapshot["counters"][0]["name"] == "events.success"


class TestGlobalCollector:
    """Test global metrics collector."""

    def setup_method(self) -> None:
        """Reset global collector before each test."""
        reset_metrics_collector()

    def test_get_metrics_collector_singleton(self):
        """get_metrics_collector should return same instance."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_reset_metrics_collector(self):
        """reset_metrics_collector should clear global instance."""
        collector = get_metrics_collector()
        collector.increment("test")

        reset_metrics_collector()
        new_collector = get_metrics_collector()

        snapshot = new_collector.get_snapshot()
        assert len(snapshot["counters"]) == 0
