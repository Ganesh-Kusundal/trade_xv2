"""Lightweight metrics interface for broker HTTP transport.

Provides a Protocol-based metrics seam (no Prometheus dependency) for recording:
- Request counts, durations, and status codes per bucket
- Rate-limit events (429 responses)
- Auth token refreshes

Pluggable via ``HttpTransport.__init__(metrics=...)``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BrokerMetrics(Protocol):
    """Protocol for broker metrics collection.

    Implementations can log to stdout, push to Prometheus/OTLP, or no-op.
    """

    def record_request(
        self,
        bucket: str,
        duration_ms: float,
        status: int,
    ) -> None:
        """Record an HTTP request to a rate-limit bucket."""
        ...

    def record_rate_limit(self, bucket: str) -> None:
        """Record a rate-limit event (HTTP 429 or local bucket timeout)."""
        ...

    def record_auth_refresh(self) -> None:
        """Record an auth token refresh event."""
        ...


class NoOpMetrics:
    """Default no-op metrics implementation (no side effects)."""

    def record_request(
        self,
        bucket: str,
        duration_ms: float,
        status: int,
    ) -> None:
        pass

    def record_rate_limit(self, bucket: str) -> None:
        pass

    def record_auth_refresh(self) -> None:
        pass


class LoggingMetrics:
    """Simple logging-based metrics (for debugging/development)."""

    def __init__(self, logger_name: str = "broker.metrics") -> None:
        import logging
        self._logger = logging.getLogger(logger_name)

    def record_request(
        self,
        bucket: str,
        duration_ms: float,
        status: int,
    ) -> None:
        self._logger.debug(
            "request bucket=%s duration=%.1fms status=%d",
            bucket,
            duration_ms,
            status,
        )

    def record_rate_limit(self, bucket: str) -> None:
        self._logger.warning("rate_limit bucket=%s", bucket)

    def record_auth_refresh(self) -> None:
        self._logger.info("auth_refresh")
