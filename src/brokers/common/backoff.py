"""Shared backoff strategy for HTTP clients.

Centralizes exponential backoff logic that was previously duplicated
in brokers/dhan/api/http_client.py and brokers/dhan/api/async_http_client.py.
"""

from __future__ import annotations


def exponential_backoff(
    attempt: int,
    base_delay_ms: float = 500.0,
    max_delay_ms: float = 5000.0,
) -> float:
    """Calculate exponential backoff delay in seconds.

    Args:
        attempt: Current attempt number (1-based).
        base_delay_ms: Base delay in milliseconds.
        max_delay_ms: Maximum delay cap in milliseconds.

    Returns:
        Delay in seconds.
    """
    delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
    return delay_ms / 1000.0
