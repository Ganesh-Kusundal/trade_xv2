"""Shim — use :mod:`infrastructure.observability.http_server`."""

from infrastructure.observability.http_server import (  # noqa: F401
    HttpObservabilityServer,
    render_prometheus_metrics,
)
