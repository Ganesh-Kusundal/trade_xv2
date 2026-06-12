"""Tests for the observability module (metrics and structured logging)."""

import json
import logging
import time
import unittest

from brokers.common.observability.logging import StructuredLogger
from brokers.common.observability.metrics import MetricsCollector, OperationMetrics


class TestTimeOperationSuccess(unittest.TestCase):
    """Verify metrics are recorded correctly for a successful function."""

    def test_time_operation_success(self) -> None:
        collector = MetricsCollector()

        def work() -> str:
            time.sleep(0.01)
            return "done"

        result = collector.time_operation("test_op", work)

        self.assertEqual(result, "done")
        all_metrics = collector.get_all()
        self.assertEqual(len(all_metrics), 1)

        metric = all_metrics[0]
        self.assertEqual(metric.operation, "test_op")
        self.assertTrue(metric.success)
        self.assertEqual(metric.error, "")
        # Latency should be at least ~10 ms
        self.assertGreaterEqual(metric.latency_ms, 8.0)


class TestTimeOperationFailure(unittest.TestCase):
    """Verify metrics are recorded correctly when the function raises."""

    def test_time_operation_failure(self) -> None:
        collector = MetricsCollector()

        def failing_work() -> None:
            time.sleep(0.01)
            raise ValueError("something broke")

        with self.assertRaises(ValueError):
            collector.time_operation("fail_op", failing_work)

        all_metrics = collector.get_all()
        self.assertEqual(len(all_metrics), 1)

        metric = all_metrics[0]
        self.assertEqual(metric.operation, "fail_op")
        self.assertFalse(metric.success)
        self.assertEqual(metric.error, "something broke")
        self.assertGreaterEqual(metric.latency_ms, 8.0)


class TestGetSummary(unittest.TestCase):
    """Verify summary calculations across multiple recorded operations."""

    def test_get_summary(self) -> None:
        collector = MetricsCollector()

        # Record 10 successful operations with varying latency
        for i in range(10):
            collector.record(
                OperationMetrics(
                    operation=f"op_{i}",
                    latency_ms=float(i * 10),
                    success=True,
                )
            )

        # Record 2 failures
        collector.record(
            OperationMetrics(
                operation="fail_0",
                latency_ms=50.0,
                success=False,
                error="err",
            )
        )
        collector.record(
            OperationMetrics(
                operation="fail_1",
                latency_ms=150.0,
                success=False,
                error="err",
            )
        )

        summary = collector.get_summary()

        self.assertEqual(summary["total_count"], 12)
        self.assertEqual(summary["success_count"], 10)
        self.assertEqual(summary["failure_count"], 2)

        # Average: (0+10+20+30+40+50+60+70+80+90+50+150) / 12 = 650/12 ~= 54.167
        self.assertAlmostEqual(summary["avg_latency_ms"], 650.0 / 12.0, places=1)

        # p95: sorted latencies = [0,10,20,30,40,50,50,60,70,80,90,150]
        # index = int(12 * 0.95) = 11 -> value 150
        self.assertAlmostEqual(summary["p95_latency_ms"], 150.0, places=1)

    def test_get_summary_empty(self) -> None:
        collector = MetricsCollector()
        summary = collector.get_summary()
        self.assertEqual(summary["total_count"], 0)
        self.assertEqual(summary["avg_latency_ms"], 0.0)


class TestClear(unittest.TestCase):
    """Verify that clear removes all recorded metrics."""

    def test_clear(self) -> None:
        collector = MetricsCollector()
        collector.record(
            OperationMetrics(
                operation="op",
                latency_ms=10.0,
                success=True,
            )
        )
        self.assertEqual(len(collector.get_all()), 1)

        collector.clear()
        self.assertEqual(len(collector.get_all()), 0)
        self.assertEqual(collector.get_summary()["total_count"], 0)


class TestStructuredLoggerInfo(unittest.TestCase):
    """Verify that info logs produce valid JSON with expected fields."""

    def test_structured_logger_info(self) -> None:
        logger = StructuredLogger("test.info.logger")

        with self.assertLogs("test.info.logger", level=logging.INFO) as captured:
            logger.info("order_placed", order_id="ABC123", quantity=100)

        self.assertEqual(len(captured.output), 1)
        # The log message is the JSON string after the level prefix
        raw_message = captured.output[0]
        # Extract JSON portion (after "INFO:test.info.logger:")
        json_str = raw_message.split(":", 2)[-1] if ":" in raw_message else raw_message
        # Find the JSON object in the string
        json_start = json_str.index("{")
        parsed = json.loads(json_str[json_start:])

        self.assertEqual(parsed["event"], "order_placed")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["order_id"], "ABC123")
        self.assertEqual(parsed["quantity"], 100)
        self.assertIn("timestamp", parsed)


class TestStructuredLoggerError(unittest.TestCase):
    """Verify that error logs produce valid JSON with error details."""

    def test_structured_logger_error(self) -> None:
        logger = StructuredLogger("test.error.logger")

        with self.assertLogs("test.error.logger", level=logging.ERROR) as captured:
            logger.error(
                "order_failed",
                error=RuntimeError("connection timeout"),
                order_id="XYZ789",
            )

        self.assertEqual(len(captured.output), 1)
        raw_message = captured.output[0]
        json_str = raw_message.split(":", 2)[-1] if ":" in raw_message else raw_message
        json_start = json_str.index("{")
        parsed = json.loads(json_str[json_start:])

        self.assertEqual(parsed["event"], "order_failed")
        self.assertEqual(parsed["level"], "ERROR")
        self.assertEqual(parsed["error_type"], "RuntimeError")
        self.assertEqual(parsed["error_message"], "connection timeout")
        self.assertEqual(parsed["order_id"], "XYZ789")
        self.assertIn("timestamp", parsed)


if __name__ == "__main__":
    unittest.main()
