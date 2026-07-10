"""CLI utility modules.

Provides reusable utilities for timeout handling, retry logic, and error formatting.

Modules:
    timeout_handler : Timeout protection for API calls
    retry_handler : Retry logic with exponential backoff
    error_formatter : User-friendly error messages
"""

from __future__ import annotations

from interface.ui.utils.error_formatter import (
    display_error,
    format_error,
    get_error_severity,
    is_retryable_error,
)
from interface.ui.utils.retry_handler import retry_with_backoff, with_retry
from interface.ui.utils.timeout_handler import with_timeout, with_timeout_async

__all__ = [
    "display_error",
    # Error formatter
    "format_error",
    "get_error_severity",
    "is_retryable_error",
    "retry_with_backoff",
    # Retry handler
    "with_retry",
    # Timeout handler
    "with_timeout",
    "with_timeout_async",
]
