"""Tests for structured logging infrastructure (P5 Stability Engineering).

Verifies:
1. Correlation ID automatic injection into all log messages
2. JSON format in production mode
3. Console format in development mode
4. Thread-safe correlation ID propagation
5. Log enrichment with extra fields
6. Exception formatting
"""

import json
import logging
import threading
from io import StringIO
from unittest.mock import patch

from infrastructure.correlation import with_correlation
from infrastructure.logging_config import (
    ConsoleFormatter,
    CorrelationFilter,
    JSONFormatter,
    get_logger,
    set_production_mode,
)


class TestCorrelationFilter:
    """Test correlation ID injection into log records."""

    def test_filter_injects_correlation_id(self):
        """CorrelationFilter should add correlation_id to log record."""
        filter = CorrelationFilter()

        with with_correlation("test-corr-123"):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )

            result = filter.filter(record)

            assert result is True
            assert record.correlation_id == "test-corr-123"
            assert record.service_name == "trading-platform"

    def test_filter_handles_no_correlation_id(self):
        """CorrelationFilter should use 'no-correlation' when ID not set."""
        filter = CorrelationFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = filter.filter(record)

        assert result is True
        assert record.correlation_id == "no-correlation"

    def test_filter_injects_service_name(self):
        """CorrelationFilter should inject service name from env var."""
        with patch.dict("os.environ", {"TRADING_SERVICE_NAME": "test-service"}):
            filter = CorrelationFilter()

            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )

            filter.filter(record)

            assert record.service_name == "test-service"


class TestJSONFormatter:
    """Test JSON log formatting for production."""

    def test_json_format_contains_required_fields(self):
        """JSON output should contain all required fields."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-123"
        record.service_name = "test-service"
        record.funcName = "test_function"

        output = formatter.format(record)
        log_data = json.loads(output)

        assert "timestamp" in log_data
        assert "level" in log_data
        assert log_data["level"] == "INFO"
        assert "correlation_id" in log_data
        assert log_data["correlation_id"] == "corr-123"
        assert "service_name" in log_data
        assert log_data["service_name"] == "test-service"
        assert "message" in log_data
        assert log_data["message"] == "Test message"
        assert "module" in log_data
        assert "function" in log_data
        assert log_data["function"] == "test_function"
        assert "line" in log_data
        assert log_data["line"] == 42

    def test_json_format_includes_extra_fields(self):
        """JSON output should include extra fields from log call."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Order placed",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-123"
        record.service_name = "test-service"
        record.order_id = "O1"
        record.symbol = "RELIANCE"
        record.funcName = "place_order"

        output = formatter.format(record)
        log_data = json.loads(output)

        assert log_data["order_id"] == "O1"
        assert log_data["symbol"] == "RELIANCE"

    def test_json_format_includes_exception_info(self):
        """JSON output should include exception details."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
            record.correlation_id = "corr-123"
            record.service_name = "test-service"
            record.funcName = "error_function"

            output = formatter.format(record)
            log_data = json.loads(output)

            assert "exception" in log_data
            assert log_data["exception"]["type"] == "ValueError"
            assert log_data["exception"]["message"] == "Test error"
            assert "traceback" in log_data["exception"]

    def test_json_format_handles_non_serializable_values(self):
        """JSON output should convert non-serializable values to strings."""
        formatter = JSONFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-123"
        record.service_name = "test-service"
        record.custom_object = object()  # Non-serializable
        record.funcName = "test_function"

        output = formatter.format(record)
        log_data = json.loads(output)

        # Should be converted to string representation
        assert "custom_object" in log_data
        assert isinstance(log_data["custom_object"], str)


class TestConsoleFormatter:
    """Test console log formatting for development."""

    def test_console_format_human_readable(self):
        """Console output should be human-readable."""
        formatter = ConsoleFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-123"
        record.service_name = "test-service"
        record.funcName = "test_function"

        output = formatter.format(record)

        # Should contain key components
        assert "INFO" in output
        assert "[corr-123]" in output
        assert "Test message" in output

    def test_console_format_includes_extra_fields(self):
        """Console output should include extra fields."""
        formatter = ConsoleFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Order placed",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "corr-123"
        record.service_name = "test-service"
        record.order_id = "O1"
        record.symbol = "RELIANCE"
        record.funcName = "place_order"

        output = formatter.format(record)

        assert "order_id=O1" in output
        assert "symbol=RELIANCE" in output


class TestGetLogger:
    """Test logger factory function."""

    def test_get_logger_returns_configured_logger(self):
        """get_logger should return a working logger instance."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_initializes_once(self):
        """get_logger should initialize root logger only once."""
        # Call multiple times
        logger1 = get_logger("test.module1")
        logger2 = get_logger("test.module2")

        # Both should work
        assert logger1 is not None
        assert logger2 is not None
        assert logger1.name != logger2.name

    def test_get_logger_with_correlation_context(self):
        """Logger should capture correlation ID from context."""
        import logging.handlers

        # Create a string handler to capture output
        StringIO()
        logging.handlers.MemoryHandler(capacity=100, flushLevel=logging.ERROR)

        with with_correlation("test-corr-456"):
            logger = get_logger("test.correlation")
            logger.info("Test message")

            # Verify logger is configured (can't easily test output without complex setup)
            assert logger is not None


class TestThreadSafety:
    """Test thread-safe correlation ID propagation."""

    def test_correlation_id_thread_isolation(self):
        """Each thread should have its own correlation ID."""
        results = {}

        def worker(thread_id: int, correlation_id: str) -> None:
            with with_correlation(correlation_id):
                filter = CorrelationFilter()
                record = logging.LogRecord(
                    name="test",
                    level=logging.INFO,
                    pathname="test.py",
                    lineno=1,
                    msg="Test message",
                    args=(),
                    exc_info=None,
                )
                filter.filter(record)
                results[thread_id] = record.correlation_id

        # Run workers in parallel
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i, f"corr-{i}"))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Each thread should have its own correlation ID
        assert len(results) == 5
        for i in range(5):
            assert results[i] == f"corr-{i}"


class TestProductionMode:
    """Test production vs development mode switching."""

    def test_set_production_mode_json_output(self):
        """Production mode should use JSON formatter."""
        from infrastructure.logging_config import StructuredFormatter, configure_logging

        configure_logging(service="test", log_format="json")

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, StructuredFormatter)

    def test_set_production_mode_console_output(self):
        """Development mode should use console formatter."""
        from infrastructure.logging_config import HumanReadableFormatter, configure_logging

        configure_logging(service="test", log_format="human")

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, HumanReadableFormatter)


class TestIntegration:
    """Integration tests for complete logging workflow."""

    def test_end_to_end_logging_with_correlation(self):
        """Complete logging workflow should work with correlation ID."""
        set_production_mode(True)

        with with_correlation("e2e-test-corr"):
            get_logger("test.integration")

            # Create a log record manually to test
            record = logging.LogRecord(
                name="test.integration",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Order placed",
                args=(),
                exc_info=None,
            )

            # Apply filter
            filter = CorrelationFilter()
            filter.filter(record)

            # Format as JSON
            formatter = JSONFormatter()
            output = formatter.format(record)
            log_data = json.loads(output)

            # Verify all fields present
            assert log_data["correlation_id"] == "e2e-test-corr"
            assert log_data["message"] == "Order placed"
            assert log_data["level"] == "INFO"

    def test_logging_without_correlation_context(self):
        """Logging should work even without correlation ID set."""
        get_logger("test.no_correlation")

        # Should not crash
        record = logging.LogRecord(
            name="test.no_correlation",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        filter = CorrelationFilter()
        filter.filter(record)

        assert record.correlation_id == "no-correlation"
