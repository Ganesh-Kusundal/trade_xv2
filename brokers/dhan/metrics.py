"""Dhan broker metrics for Prometheus exposition."""
from __future__ import annotations

from infrastructure.metrics.registry import metrics_registry

dhan_request_total = metrics_registry.counter(
    "dhan_request_total",
    "Total HTTP requests to Dhan API",
)
dhan_request_duration_seconds = metrics_registry.histogram(
    "dhan_request_duration_seconds",
    "Dhan API request latency in seconds",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
dhan_errors_total = metrics_registry.counter(
    "dhan_errors_total",
    "Total Dhan API errors by type",
)
dhan_rate_limit_retries_total = metrics_registry.counter(
    "dhan_rate_limit_retries_total",
    "Total Dhan rate limit retries",
)
