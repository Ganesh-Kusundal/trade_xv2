"""Middleware for TradeXV2 API.

Provides:
- ``RequestLoggingMiddleware`` — correlation IDs, timing, and HTTP metrics.
- ``RateLimitMiddleware`` — per-IP sliding-window rate limiting.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class HttpRequestMetrics:
    """Thread-safe in-process HTTP metrics for Prometheus exposition.

    Counters:
        request_total{method, path, status} — total requests.
        request_duration_ms_sum{method, path, status} — cumulative latency.
        request_duration_ms_count{method, path, status} — count of latencies.

    Paths are normalised by stripping numeric IDs (e.g. ``/orders/123``
    becomes ``/orders/{id}``) to avoid high-cardinality labels.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total: dict[tuple[str, str, str], int] = defaultdict(int)
        self._duration_sum: dict[tuple[str, str, str], float] = defaultdict(float)
        self._duration_count: dict[tuple[str, str, str], int] = defaultdict(int)
        self._active_requests = 0

    def record(self, method: str, path: str, status: int, duration_ms: float) -> None:
        key = (method, path, str(status))
        with self._lock:
            self._total[key] += 1
            self._duration_sum[key] += duration_ms
            self._duration_count[key] += 1

    def inc_active(self) -> None:
        with self._lock:
            self._active_requests += 1

    def dec_active(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    @property
    def active_requests(self) -> int:
        with self._lock:
            return self._active_requests

    def snapshot(self) -> dict[str, dict[str, dict[str, float]]]:
        """Return a JSON-serialisable snapshot of all counters."""
        with self._lock:
            return {
                "total": {f"{m}|{p}|{s}": v for (m, p, s), v in sorted(self._total.items())},
                "duration_ms_sum": {
                    f"{m}|{p}|{s}": v for (m, p, s), v in sorted(self._duration_sum.items())
                },
                "duration_ms_count": {
                    f"{m}|{p}|{s}": v for (m, p, s), v in sorted(self._duration_count.items())
                },
                "active_requests": self.active_requests,
            }

    def render_prometheus(self) -> str:
        """Render Prometheus text exposition format.

        Takes a single snapshot under one lock acquisition to ensure
        consistent counters across all metrics.
        """
        lines: list[str] = []

        with self._lock:
            total_copy = dict(self._total)
            dur_sum_copy = dict(self._duration_sum)
            dur_count_copy = dict(self._duration_count)
            active = self._active_requests

        lines.append(
            "# HELP tradexv2_http_requests_total Total HTTP requests by method, path, status."
        )
        lines.append("# TYPE tradexv2_http_requests_total counter")
        for (method, path, status), count in sorted(total_copy.items()):
            labels = f'method="{method}", path="{path}", status="{status}"'
            lines.append(f"tradexv2_http_requests_total{{{labels}}} {count}")

        lines.append(
            "# HELP tradexv2_http_request_duration_ms_sum Cumulative request duration in ms."
        )
        lines.append("# TYPE tradexv2_http_request_duration_ms_sum counter")
        for (method, path, status), val in sorted(dur_sum_copy.items()):
            labels = f'method="{method}", path="{path}", status="{status}"'
            lines.append(f"tradexv2_http_request_duration_ms_sum{{{labels}}} {val:.1f}")

        lines.append(
            "# HELP tradexv2_http_request_duration_ms_count Request duration sample count."
        )
        lines.append("# TYPE tradexv2_http_request_duration_ms_count counter")
        for (method, path, status), val in sorted(dur_count_copy.items()):
            labels = f'method="{method}", path="{path}", status="{status}"'
            lines.append(f"tradexv2_http_request_duration_ms_count{{{labels}}} {val}")

        lines.append("# HELP tradexv2_http_active_requests Currently active HTTP requests.")
        lines.append("# TYPE tradexv2_http_active_requests gauge")
        lines.append(f"tradexv2_http_active_requests {active}")

        return "\n".join(lines) + "\n"


# Module-level singleton — initialised once per process.
http_metrics = HttpRequestMetrics()


def _normalise_path(path: str) -> str:
    """Replace numeric path segments with ``{id}`` to bound cardinality.

    ``/orders/12345`` → ``/orders/{id}``
    ``/replay/sessions/abc-123/play`` → ``/replay/sessions/{id}/play``
    """
    parts = path.split("/")
    result: list[str] = []
    for part in parts:
        # Skip query-string from the last segment
        clean = part.split("?", 1)[0]
        if clean.isdigit():
            result.append("{id}")
        else:
            result.append(clean)
    return "/".join(result)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that logs every request and records metrics.

    Features:
    - Propagates or generates ``X-Request-ID``.
    - Logs request method, path, status code, and duration in ms.
    - Records Prometheus-compatible counters via ``http_metrics``.
    - Skips health probe paths (/, /healthz, /readyz) to reduce noise.
    """

    _SKIP_PATHS = frozenset(
        {
            "/",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/v1/health",
            "/api/v1/health/readyz",
            "/api/v1/health/metrics",
            "/api/v1/health/metrics/prometheus",
        }
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Correlation / request ID
        request_id = request.headers.get("X-Request-ID") or request.headers.get(
            "X-Correlation-ID", ""
        )
        if not request_id:
            request_id = uuid.uuid4().hex[:16]

        method = request.method
        raw_path = request.url.path
        normalised_path = _normalise_path(raw_path)

        # Skip noisy health probes
        skip = raw_path in self._SKIP_PATHS

        start = time.perf_counter()
        status_code = 500
        try:
            http_metrics.inc_active()
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
        except Exception:
            status_code = 500
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            http_metrics.dec_active()
            if not skip:
                http_metrics.record(method, normalised_path, status_code, elapsed_ms)
                logger.info(
                    "%s %s %d %.1fms [%s]",
                    method,
                    raw_path,
                    status_code,
                    elapsed_ms,
                    request_id,
                )

        return response


class _SlidingWindowCounter:
    """Thread-safe per-key sliding window counter for rate limiting.

    Uses a simple sliding window: each key tracks the timestamps of
    recent requests within the window. Expired entries are pruned on
    access so memory stays bounded.
    """

    def __init__(self, window_seconds: float) -> None:
        self._window = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int) -> tuple[bool, int]:
        """Check if a request is allowed.

        Returns (allowed, remaining) where remaining is the number of
        requests left in the current window (0 if denied).
        """
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            timestamps = self._buckets[key]
            # Prune expired entries
            self._buckets[key] = timestamps = [
                t for t in timestamps if t > cutoff
            ]
            remaining = max_requests - len(timestamps)
            if remaining > 0:
                timestamps.append(now)
                return True, remaining - 1
            return False, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting middleware using a sliding window.

    When ``max_requests`` is 0, the middleware is disabled and passes
    all requests through without overhead.

    Returns HTTP 429 with ``Retry-After`` and ``X-RateLimit-*`` headers
    when the limit is exceeded.
    """

    def __init__(
        self,
        app: Any,
        max_requests: int = 0,
        window_seconds: float = 60.0,
    ) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._counter: _SlidingWindowCounter | None = (
            _SlidingWindowCounter(window_seconds) if max_requests > 0 else None
        )

    @staticmethod
    def _client_ip(request: Request) -> str:
        """Extract client IP, preferring X-Forwarded-For in trusted proxies."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._counter is None:
            return await call_next(request)

        # Skip health/metrics probes
        path = request.url.path
        if path in RequestLoggingMiddleware._SKIP_PATHS:
            return await call_next(request)

        ip = self._client_ip(request)
        allowed, remaining = self._counter.is_allowed(ip, self._max_requests)

        if not allowed:
            retry_after = int(self._window)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self._max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(int(self._window)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(int(self._window))
        return response
