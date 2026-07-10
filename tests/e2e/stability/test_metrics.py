"""Tests for metrics collection infrastructure (P5 Stability Engineering).

Verifies:
1. Counter metrics track monotonically increasing values
2. Gauge metrics track current values
3. Histogram metrics track distributions
4. Metrics are thread-safe
"""

import threading

from infrastructure.metrics import Counter, Gauge, Histogram, MetricsRegistry, metrics_registry
from infrastructure.metrics.types import Timer


class TestCounter:
    def test_counter_inc(self):
        counter = Counter("test", "test counter")
        counter.inc()
        counter.inc(5)
        assert counter.value == 6

    def test_counter_reset(self):
        counter = Counter("test")
        counter.inc(10)
        counter.reset()
        assert counter.value == 0

    def test_counter_thread_safety(self):
        counter = Counter("thread_test")

        def worker():
            for _ in range(1000):
                counter.inc()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert counter.value == 10000


class TestGauge:
    def test_gauge_set(self):
        gauge = Gauge("test")
        gauge.set(42.5)
        assert gauge.value == 42.5

    def test_gauge_inc_dec(self):
        gauge = Gauge("test")
        gauge.set(10)
        gauge.inc(5)
        gauge.dec(3)
        assert gauge.value == 12.0

    def test_gauge_thread_safety(self):
        gauge = Gauge("thread_test")

        def worker():
            for _ in range(1000):
                gauge.inc()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert gauge.value == 10000


class TestHistogram:
    def test_histogram_observe(self):
        h = Histogram("test")
        h.observe(10.0)
        h.observe(20.0)
        h.observe(30.0)
        assert len(h.values) == 3
        assert sum(h.values) == 60.0

    def test_histogram_reset(self):
        h = Histogram("test")
        h.observe(100.0)
        h.reset()
        assert len(h.values) == 0

    def test_histogram_thread_safety(self):
        h = Histogram("thread_test")

        def worker():
            for i in range(100):
                h.observe(float(i))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(h.values) == 1000


class TestTimer:
    def test_timer_context_manager(self):
        timer = Timer("test")
        with timer.time():
            pass
        assert len(timer.values) == 1
        assert timer.values[0] >= 0


class TestMetricsRegistry:
    def test_factory_methods(self):
        reg = MetricsRegistry()
        c = reg.counter("orders_total", "Total orders")
        c.inc(5)
        snap = reg.snapshot()
        assert snap["counters"]["orders_total"] == 5

    def test_snapshot(self):
        reg = MetricsRegistry()
        reg.counter("c1").inc(1)
        reg.gauge("g1").set(42)
        reg.histogram("h1").observe(1.0)
        snap = reg.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "histograms" in snap

    def test_reset_all(self):
        reg = MetricsRegistry()
        reg.counter("c1").inc(10)
        reg.reset_all()
        assert reg.snapshot()["counters"]["c1"] == 0


class TestGlobalRegistry:
    def test_singleton(self):
        from infrastructure.metrics.registry import metrics_registry as r1
        from infrastructure.metrics.registry import metrics_registry as r2
        assert r1 is r2
