"""Error formatter for CLI commands.

Converts raw exceptions to user-friendly, actionable error messages.

Usage:
    from cli.utils.error_formatter import format_error, display_error

    try:
        quote = gw.quote("RELIANCE")
    except Exception as exc:
        msg = format_error(exc)
        console.print(f"[red]{msg}[/red]")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_error(exc: Exception) -> str:
    """Convert exception to user-friendly error message.

    Parameters
    ----------
    exc :
        Exception to format.

    Returns
    -------
    str
        User-friendly error message with actionable guidance.

    Examples
    --------
    >>> from cli.utils.error_formatter import format_error
    >>>
    >>> try:
    ...     gw.quote("RELIANCE")
    ... except Exception as e:
    ...     print(format_error(e))
    "Authentication failed. Token may be expired. Run: tradex doctor"
    """
    error_str = str(exc).lower()

    # Authentication errors
    if "401" in error_str or "unauthorized" in error_str or "invalid token" in error_str:
        return "Authentication failed. Token may be expired. Run: tradex doctor"

    # Rate limit errors
    if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
        return "Rate limit exceeded. Retry after 60s or use --broker with different account."

    # Network errors
    if "connection" in error_str or "network" in error_str or "refused" in error_str:
        return "Network error. Check internet connection and broker API status."

    if "timeout" in error_str or "timed out" in error_str:
        return "Request timed out. Broker API may be slow. Retry or use --quick mode."

    # Instrument errors
    if "instrument" in error_str and "not found" in error_str:
        return "Symbol not found. Use: tradex search <symbol> to find valid symbols."

    if "symbol" in error_str and "not found" in error_str:
        return "Symbol not found. Use: tradex search <symbol> to find valid symbols."

    # Order errors
    if "risk" in error_str and "rejected" in error_str:
        return "Order rejected by risk manager. Check: tradex risk status"

    if "margin" in error_str and "insufficient" in error_str:
        return "Insufficient margin. Check: tradex funds"

    if "order" in error_str and "invalid" in error_str:
        return "Invalid order parameters. Check symbol, quantity, and order type."

    # File errors
    if "no such file" in error_str or "file not found" in error_str:
        return "File not found. Check the file path and try again."

    if "permission denied" in error_str:
        return "Permission denied. Check file permissions and try again."

    # Data errors
    if "no data" in error_str or "empty" in error_str:
        return "No data available for the requested symbol/date range."

    # Broker-specific errors
    if "dhan" in error_str and "token" in error_str:
        return "Dhan API token error. Run: tradex doctor to diagnose."

    if "upstox" in error_str and "token" in error_str:
        return "Upstox API token error. Run: tradex doctor to diagnose."

    # Generic fallback
    return f"Unexpected error: {exc}"


def display_error(
    exc: Exception,
    console: Any,
    *,
    prefix: str = "Error",
    show_details: bool = False,
) -> None:
    """Display formatted error message to console.

    Parameters
    ----------
    exc :
        Exception to display.
    console :
        Rich console instance.
    prefix :
        Error prefix (default: "Error").
    show_details :
        If True, also show raw exception details.

    Examples
    --------
    >>> from cli.utils.error_formatter import display_error
    >>>
    >>> try:
    ...     gw.quote("RELIANCE")
    ... except Exception as e:
    ...     display_error(e, console)
    """
    user_msg = format_error(exc)
    console.print(f"[red]❌ {prefix}: {user_msg}[/red]")

    if show_details:
        logger.exception("error_details", extra={"error": str(exc)})
        console.print(f"[dim]Details: {exc}[/dim]")


def is_retryable_error(exc: Exception) -> bool:
    """Determine if an error is retryable (transient).

    Parameters
    ----------
    exc :
        Exception to check.

    Returns
    -------
    bool
        True if the error is likely transient and worth retrying.

    Examples
    --------
    >>> from cli.utils.error_formatter import is_retryable_error
    >>>
    >>> if is_retryable_error(exc):
    ...     # Retry the operation
    ...     pass
    """
    error_str = str(exc).lower()

    # Network-related errors are usually transient
    return bool(
        any(
            keyword in error_str
            for keyword in [
                "connection",
                "timeout",
                "timed out",
                "network",
                "refused",
                "429",
                "rate limit",
                "502",
                "503",
                "504",
            ]
        )
    )


def get_error_severity(exc: Exception) -> str:
    """Determine error severity level.

    Parameters
    ----------
    exc :
        Exception to classify.

    Returns
    -------
    str
        One of: "critical", "error", "warning", "info"

    Examples
    --------
    >>> from cli.utils.error_formatter import get_error_severity
    >>>
    >>> severity = get_error_severity(exc)
    >>> if severity == "critical":
    ...     # Handle critical error
    ...     pass
    """
    error_str = str(exc).lower()

    # Critical: authentication, authorization
    if any(keyword in error_str for keyword in ["401", "unauthorized", "forbidden", "403"]):
        return "critical"

    # Error: order rejection, margin issues
    if any(
        keyword in error_str for keyword in ["rejected", "margin", "insufficient", "invalid order"]
    ):
        return "error"

    # Warning: rate limits, timeouts, no data
    if any(
        keyword in error_str for keyword in ["429", "rate limit", "timeout", "no data", "empty"]
    ):
        return "warning"

    # Info: everything else
    return "info"
