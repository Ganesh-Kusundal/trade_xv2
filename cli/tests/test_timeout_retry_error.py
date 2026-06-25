"""Tests for timeout, retry, and error handling utilities."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from cli.utils.error_formatter import (
    display_error,
    format_error,
    get_error_severity,
    is_retryable_error,
)
from cli.utils.retry_handler import retry_with_backoff, with_retry
from cli.utils.timeout_handler import with_timeout, with_timeout_async

# ── Timeout Handler Tests ─────────────────────────────────────────────────


class TestWithTimeout:
    """Tests for with_timeout function."""

    def test_successful_execution_within_timeout(self):
        """Test function completes within timeout."""

        def fast_function():
            return "success"

        result = with_timeout(fast_function, timeout_seconds=5)
        assert result == "success"

    def test_timeout_raises_timeout_error(self):
        """Test function that exceeds timeout raises TimeoutError."""

        def slow_function():
            time.sleep(10)
            return "should not reach here"

        with pytest.raises(TimeoutError, match="slow_function timed out after 1s"):
            with_timeout(slow_function, timeout_seconds=1)

    def test_timeout_with_args_and_kwargs(self):
        """Test function with arguments."""

        def add_numbers(a, b, multiplier=1):
            return (a + b) * multiplier

        result = with_timeout(add_numbers, timeout_seconds=5, a=2, b=3, multiplier=2)
        assert result == 10

    def test_timeout_preserves_exceptions(self):
        """Test that non-timeout exceptions are preserved."""

        def failing_function():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            with_timeout(failing_function, timeout_seconds=5)

    def test_timeout_default_30_seconds(self):
        """Test default timeout is 30 seconds."""

        # We can't test 30s directly, but verify the function accepts it
        def quick_func():
            return True

        assert with_timeout(quick_func) is True


class TestWithTimeoutAsync:
    """Tests for with_timeout_async function."""

    def test_successful_execution(self):
        """Test successful execution without timeout."""

        def fast_function():
            return "success"

        result = with_timeout_async(fast_function, timeout_seconds=5)
        assert result == "success"

    def test_timeout_with_fallback(self):
        """Test timeout with fallback function."""

        def slow_function():
            time.sleep(10)
            return "should not reach"

        def fallback():
            return "fallback value"

        result = with_timeout_async(slow_function, timeout_seconds=1, on_timeout=fallback)
        assert result == "fallback value"

    def test_timeout_without_fallback_raises(self):
        """Test timeout without fallback raises TimeoutError."""

        def slow_function():
            time.sleep(10)

        with pytest.raises(TimeoutError):
            with_timeout_async(slow_function, timeout_seconds=1)


# ── Retry Handler Tests ──────────────────────────────────────────────────


class TestWithRetryDecorator:
    """Tests for with_retry decorator."""

    def test_successful_first_attempt(self):
        """Test function succeeds on first attempt."""
        call_count = 0

        @with_retry(max_retries=3)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_connection_error(self):
        """Test retry on ConnectionError."""
        call_count = 0

        @with_retry(max_retries=3, backoff_factor=0.01)
        def failing_then_succeeding():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection failed")
            return "success"

        result = failing_then_succeeding()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted_raises_last_error(self):
        """Test that exhausted retries raise the last error."""
        call_count = 0

        @with_retry(max_retries=3, backoff_factor=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError, match="always fails"):
            always_fails()

        assert call_count == 3

    def test_non_retryable_error_not_retried(self):
        """Test that non-retryable errors are not retried."""
        call_count = 0

        @with_retry(max_retries=3, backoff_factor=0.01)
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            raises_value_error()

        assert call_count == 1

    def test_custom_retryable_errors(self):
        """Test custom retryable error types."""
        call_count = 0

        @with_retry(
            max_retries=3,
            backoff_factor=0.01,
            retryable_errors=(ValueError,),
        )
        def raises_value_error_retried():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry this")
            return "success"

        result = raises_value_error_retried()
        assert result == "success"
        assert call_count == 2

    def test_on_retry_callback(self):
        """Test on_retry callback is invoked."""
        call_count = 0
        retry_calls = []

        @with_retry(
            max_retries=3,
            backoff_factor=0.01,
            on_retry=lambda attempt, exc, wait: retry_calls.append((attempt, str(exc), wait)),
        )
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("test error")

        with pytest.raises(ConnectionError):
            failing_function()

        assert len(retry_calls) == 2  # Called on attempts 1 and 2
        assert retry_calls[0][0] == 0
        assert retry_calls[1][0] == 1

    def test_decorator_without_parentheses(self):
        """Test @with_retry syntax without parentheses."""
        call_count = 0

        @with_retry
        def simple_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("retry")
            return "success"

        result = simple_function()
        assert result == "success"
        assert call_count == 2


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    def test_successful_execution(self):
        """Test successful execution without retries."""

        def success():
            return "ok"

        result = retry_with_backoff(success, max_retries=3)
        assert result == "ok"

    def test_retry_then_success(self):
        """Test retries then success."""
        call_count = 0

        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            return "success"

        result = retry_with_backoff(fail_then_succeed, max_retries=3, backoff_factor=0.01)
        assert result == "success"
        assert call_count == 2

    def test_all_retries_fail(self):
        """Test all retries exhausted."""
        call_count = 0

        def always_fail():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError, match="timeout"):
            retry_with_backoff(always_fail, max_retries=3, backoff_factor=0.01)

        assert call_count == 3


# ── Error Formatter Tests ────────────────────────────────────────────────


class TestFormatError:
    """Tests for format_error function."""

    def test_authentication_error(self):
        """Test authentication error formatting."""
        exc = Exception("401 Unauthorized")
        msg = format_error(exc)
        assert "Authentication failed" in msg
        assert "tradex doctor" in msg

    def test_rate_limit_error(self):
        """Test rate limit error formatting."""
        exc = Exception("429 Too Many Requests")
        msg = format_error(exc)
        assert "Rate limit exceeded" in msg

    def test_network_error(self):
        """Test network error formatting."""
        exc = ConnectionError("Connection refused")
        msg = format_error(exc)
        assert "Network error" in msg

    def test_timeout_error(self):
        """Test timeout error formatting."""
        exc = TimeoutError("Request timed out")
        msg = format_error(exc)
        assert "timed out" in msg.lower()

    def test_instrument_not_found(self):
        """Test instrument not found error."""
        exc = Exception("Instrument not found: RELIANCE")
        msg = format_error(exc)
        assert "Symbol not found" in msg
        assert "tradex search" in msg

    def test_risk_rejection(self):
        """Test risk manager rejection."""
        exc = Exception("Order rejected by risk manager")
        msg = format_error(exc)
        assert "risk manager" in msg.lower()
        assert "tradex risk status" in msg

    def test_insufficient_margin(self):
        """Test insufficient margin error."""
        exc = Exception("Insufficient margin for order")
        msg = format_error(exc)
        assert "Insufficient margin" in msg
        assert "tradex funds" in msg

    def test_file_not_found(self):
        """Test file not found error."""
        exc = FileNotFoundError("No such file: /tmp/test.csv")
        msg = format_error(exc)
        assert "File not found" in msg

    def test_generic_error(self):
        """Test generic error fallback."""
        exc = Exception("Some unexpected error")
        msg = format_error(exc)
        assert "Unexpected error" in msg


class TestDisplayError:
    """Tests for display_error function."""

    def test_display_error_basic(self):
        """Test basic error display."""
        mock_console = MagicMock()
        exc = Exception("401 Unauthorized")

        display_error(exc, mock_console)

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Authentication failed" in call_args

    def test_display_error_with_details(self):
        """Test error display with details."""
        mock_console = MagicMock()
        exc = ValueError("test error")

        display_error(exc, mock_console, show_details=True)

        assert mock_console.print.call_count == 2

    def test_display_error_custom_prefix(self):
        """Test error display with custom prefix."""
        mock_console = MagicMock()
        exc = Exception("test")

        display_error(exc, mock_console, prefix="Custom Error")

        call_args = mock_console.print.call_args[0][0]
        assert "Custom Error" in call_args


class TestIsRetryableError:
    """Tests for is_retryable_error function."""

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Connection refused",
            "Request timed out",
            "Network error",
            "Connection reset",
            "429 Too Many Requests",
            "Rate limit exceeded",
            "502 Bad Gateway",
            "503 Service Unavailable",
            "504 Gateway Timeout",
        ],
    )
    def test_retryable_errors(self, error_msg):
        """Test various retryable errors."""
        exc = Exception(error_msg)
        assert is_retryable_error(exc) is True

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Invalid symbol",
            "Authentication failed",
            "Insufficient margin",
            "Order rejected",
        ],
    )
    def test_non_retryable_errors(self, error_msg):
        """Test non-retryable errors."""
        exc = Exception(error_msg)
        assert is_retryable_error(exc) is False


class TestGetErrorSeverity:
    """Tests for get_error_severity function."""

    def test_critical_severity(self):
        """Test critical error severity."""
        exc = Exception("401 Unauthorized")
        assert get_error_severity(exc) == "critical"

    def test_error_severity(self):
        """Test error severity."""
        exc = Exception("Order rejected by risk manager")
        assert get_error_severity(exc) == "error"

    def test_warning_severity(self):
        """Test warning severity."""
        exc = Exception("429 Rate limit exceeded")
        assert get_error_severity(exc) == "warning"

    def test_info_severity(self):
        """Test info severity (default)."""
        exc = Exception("Some generic error")
        assert get_error_severity(exc) == "info"
