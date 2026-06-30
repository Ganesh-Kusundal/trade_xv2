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
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ErrorPattern:
    keywords: tuple[str, ...]
    match_all: bool
    user_message: str
    severity: str
    retryable: bool


_ERROR_PATTERNS: list[_ErrorPattern] = [
    _ErrorPattern(("401", "unauthorized", "invalid token"), False,
                  "Authentication failed. Token may be expired. Run: tradex doctor",
                  "critical", False),
    _ErrorPattern(("forbidden", "403"), False,
                  "Authentication failed. Token may be expired. Run: tradex doctor",
                  "critical", False),
    _ErrorPattern(("429", "rate limit", "too many requests"), False,
                  "Rate limit exceeded. Retry after 60s or use --broker with different account.",
                  "warning", True),
    _ErrorPattern(("connection", "network", "refused"), False,
                  "Network error. Check internet connection and broker API status.",
                  "warning", True),
    _ErrorPattern(("timeout", "timed out"), False,
                  "Request timed out. Broker API may be slow. Retry or use --quick mode.",
                  "warning", True),
    _ErrorPattern(("502", "503", "504"), False,
                  "Broker API unavailable. Retry in a few moments.",
                  "warning", True),
    _ErrorPattern(("instrument", "not found"), True,
                  "Symbol not found. Use: tradex search <symbol> to find valid symbols.",
                  "error", False),
    _ErrorPattern(("symbol", "not found"), True,
                  "Symbol not found. Use: tradex search <symbol> to find valid symbols.",
                  "error", False),
    _ErrorPattern(("risk", "rejected"), True,
                  "Order rejected by risk manager. Check: tradex risk status",
                  "error", False),
    _ErrorPattern(("margin", "insufficient"), True,
                  "Insufficient margin. Check: tradex funds",
                  "error", False),
    _ErrorPattern(("order", "invalid"), True,
                  "Invalid order parameters. Check symbol, quantity, and order type.",
                  "error", False),
    _ErrorPattern(("no such file", "file not found"), False,
                  "File not found. Check the file path and try again.",
                  "error", False),
    _ErrorPattern(("permission denied",), False,
                  "Permission denied. Check file permissions and try again.",
                  "error", False),
    _ErrorPattern(("no data", "empty"), False,
                  "No data available for the requested symbol/date range.",
                  "warning", False),
    _ErrorPattern(("dhan", "token"), True,
                  "Dhan API token error. Run: tradex doctor to diagnose.",
                  "critical", False),
    _ErrorPattern(("upstox", "token"), True,
                  "Upstox API token error. Run: tradex doctor to diagnose.",
                  "critical", False),
]


def _match(error_str: str, pattern: _ErrorPattern) -> bool:
    if pattern.match_all:
        return all(kw in error_str for kw in pattern.keywords)
    return any(kw in error_str for kw in pattern.keywords)


def format_error(exc: Exception) -> str:
    """Convert exception to user-friendly error message."""
    error_str = str(exc).lower()
    for pattern in _ERROR_PATTERNS:
        if _match(error_str, pattern):
            return pattern.user_message
    return f"Unexpected error: {exc}"


def display_error(
    exc: Exception,
    console: Any,
    *,
    prefix: str = "Error",
    show_details: bool = False,
) -> None:
    """Display formatted error message to console."""
    user_msg = format_error(exc)
    console.print(f"[red]\u274c {prefix}: {user_msg}[/red]")

    if show_details:
        logger.exception("error_details", extra={"error": str(exc)})
        console.print(f"[dim]Details: {exc}[/dim]")


def is_retryable_error(exc: Exception) -> bool:
    """Determine if an error is retryable (transient)."""
    error_str = str(exc).lower()
    return any(_match(error_str, p) for p in _ERROR_PATTERNS if p.retryable)


def get_error_severity(exc: Exception) -> str:
    """Determine error severity level: critical, error, warning, or info."""
    error_str = str(exc).lower()
    for pattern in _ERROR_PATTERNS:
        if _match(error_str, pattern):
            return pattern.severity
    return "info"
