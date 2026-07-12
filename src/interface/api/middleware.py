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

from infrastructure.correlation import set_current_correlation_id

logger = logging.getLogger(__name__)


class HttpRequestMetrics:
    """Thread-safe HTTP metrics backed by the central MetricsRegistry.

    Uses labelled metrics for dynamic label combinations (method, path, status).
    Paths are normalised by stripping numeric IDs to avoid high-cardinality labels.
    """

    def __init__(self) -> None:
        from infrastructure.metrics.registry import metrics_registry

        self._request_total = metrics_registry.labelled_counter(
            "http_requests_total",
            "Total HTTP requests by method, path, status.",
            label_names=("method", "path", "status"),
        )
        self._request_duration = metrics_registry.labelled_histogram(
            "http_request_duration_ms",
            "HTTP request duration in milliseconds.",
            label_names=("method", "path", "status"),
            buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
        )
        self._active_requests = metrics_registry.labelled_gauge(
            "http_active_requests",
            "Currently active HTTP requests.",
            label_names=(),
        )

    def record(self, method: str, path: str, status: int, duration_ms: float) -> None:
        self._request_total.inc(method=method, path=path, status=str(status))
        self._request_duration.observe(duration_ms, method=method, path=path, status=str(status))

    def inc_active(self) -> None:
        self._active_requests.inc()

    def dec_active(self) -> None:
        self._active_requests.dec()

    @property
    def active_requests(self) -> int:
        return int(self._active_requests.get())

    def snapshot(self) -> dict[str, dict[str, dict[str, float]]]:
        """Return a JSON-serialisable snapshot of all counters."""
        total_series = self._request_total.snapshot()
        duration_series = self._request_duration.snapshot()

        total: dict[str, dict[str, dict[str, float]]] = {}
        dur_sum: dict[str, dict[str, dict[str, float]]] = {}
        dur_count: dict[str, dict[str, dict[str, float]]] = {}

        for (method, path, status), count in total_series.items():
            total.setdefault(method, {}).setdefault(path, {})[status] = count

        for (method, path, status), values in duration_series.items():
            dur_sum.setdefault(method, {}).setdefault(path, {})[status] = sum(values)
            dur_count.setdefault(method, {}).setdefault(path, {})[status] = len(values)

        return {
            "total": {
                f"{m}|{p}|{s}": v
                for m, paths in total.items()
                for p, statuses in paths.items()
                for s, v in statuses.items()
            },
            "duration_ms_sum": {
                f"{m}|{p}|{s}": v
                for m, paths in dur_sum.items()
                for p, statuses in paths.items()
                for s, v in statuses.items()
            },
            "duration_ms_count": {
                f"{m}|{p}|{s}": v
                for m, paths in dur_count.items()
                for p, statuses in paths.items()
                for s, v in statuses.items()
            },
            "active_requests": int(self._active_requests.get()),
        }

    def render_prometheus(self) -> str:
        """Render Prometheus text exposition format.

        Delegates to the central registry's labelled metrics for consistent output.
        """
        lines: list[str] = []

        total_series = self._request_total.snapshot()
        lines.append(
            "# HELP tradexv2_http_requests_total Total HTTP requests by method, path, status."
        )
        lines.append("# TYPE tradexv2_http_requests_total counter")
        for (method, path, status), count in sorted(total_series.items()):
            labels = f'method="{method}", path="{path}", status="{status}"'
            lines.append(f"tradexv2_http_requests_total{{{labels}}} {int(count)}")

        duration_series = self._request_duration.snapshot()
        lines.append(
            "# HELP tradexv2_http_request_duration_ms_sum Cumulative request duration in ms."
        )
        lines.append("# TYPE tradexv2_http_request_duration_ms_sum counter")
        for (method, path, status), values in sorted(duration_series.items()):
            labels = f'method="{method}", path="{path}", status="{status}"'
            lines.append(f"tradexv2_http_request_duration_ms_sum{{{labels}}} {sum(values):.1f}")

        lines.append(
            "# HELP tradexv2_http_request_duration_ms_count Request duration sample count."
        )
        lines.append("# TYPE tradexv2_http_request_duration_ms_count counter")
        for (method, path, status), values in sorted(duration_series.items()):
            labels = f'method="{method}", path="{path}", status="{status}"'
            lines.append(f"tradexv2_http_request_duration_ms_count{{{labels}}} {len(values)}")

        active = int(self._active_requests.get())
        lines.append("# HELP tradexv2_http_active_requests Currently active HTTP requests.")
        lines.append("# TYPE tradexv2_http_active_requests gauge")
        lines.append(f"tradexv2_http_active_requests {active}")

        return "\n".join(lines) + "\n"


# Module-level singleton — initialised once per process.
http_metrics = HttpRequestMetrics()


SKIP_PATHS = frozenset(
    {
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/health",
        "/api/v1/health/readyz",
        "/api/v1/health/ready",
        "/api/v1/health/metrics",
        "/api/v1/health/metrics/prometheus",
    }
)


def _is_id_like(segment: str) -> bool:
    """Return True for path segments that look like dynamic IDs."""
    if not segment:
        return False
    if segment.isdigit():
        return True
    return "-" in segment and any(c.isdigit() for c in segment)


def _normalise_path(path: str) -> str:
    """Replace dynamic path segments with ``{id}`` to bound cardinality.

    ``/orders/12345`` → ``/orders/{id}``
    ``/replay/sessions/abc-123/play`` → ``/replay/sessions/{id}/play``
    """
    parts = path.split("/")
    result: list[str] = []
    for part in parts:
        clean = part.split("?", 1)[0]
        if _is_id_like(clean):
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

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Correlation / request ID
        request_id = request.headers.get("X-Request-ID") or request.headers.get(
            "X-Correlation-ID", ""
        )
        if not request_id:
            request_id = uuid.uuid4().hex[:16]

        set_current_correlation_id(request_id)

        method = request.method
        raw_path = request.url.path
        normalised_path = _normalise_path(raw_path)

        skip = raw_path in SKIP_PATHS

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

    P1-6 fix: Added periodic cleanup of expired buckets and max bucket
    count to prevent unbounded memory growth from unique IP addresses.
    """

    _CLEANUP_INTERVAL = 1000  # Run cleanup every 1000 requests
    _MAX_BUCKETS = 50_000  # Maximum number of unique IPs to track

    def __init__(self, window_seconds: float) -> None:
        self._window = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._request_count = 0

    def is_allowed(self, key: str, max_requests: int) -> tuple[bool, int]:
        """Check if a request is allowed.

        Returns (allowed, remaining) where remaining is the number of
        requests left in the current window (0 if denied).
        """
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            self._request_count += 1
            # P1-6: Periodic cleanup to prevent unbounded memory growth
            if self._request_count % self._CLEANUP_INTERVAL == 0:
                self._cleanup_expired(now)

            timestamps = self._buckets[key]
            # Prune expired entries for this key
            self._buckets[key] = timestamps = [
                t for t in timestamps if t > cutoff
            ]
            # Remove empty buckets entirely
            if not timestamps:
                del self._buckets[key]
                # Record this request in a new bucket to prevent rate-limit bypass
                self._buckets[key] = [now]
                return True, max_requests - 1

            remaining = max_requests - len(timestamps)
            if remaining > 0:
                timestamps.append(now)
                return True, remaining - 1
            return False, 0

    def _cleanup_expired(self, now: float) -> None:
        """Remove all expired buckets. Must be called with lock held.

        P1-6: Prevents unbounded memory growth from unique IP addresses.
        """
        cutoff = now - self._window
        expired_keys = [
            key for key, timestamps in self._buckets.items()
            if not timestamps or all(t <= cutoff for t in timestamps)
        ]
        for key in expired_keys:
            del self._buckets[key]
        # Safety valve: if still too many buckets, clear all
        if len(self._buckets) > self._MAX_BUCKETS:
            self._buckets.clear()


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
        if path in SKIP_PATHS:
            return await call_next(request)

        # Skip WebSocket upgrade requests
        if request.headers.get("connection", "").lower() == "upgrade":
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
