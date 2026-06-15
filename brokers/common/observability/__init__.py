"""Observability module — EventMetrics, HTTP server, and Prometheus renderer.

The EventMetrics class is the canonical in-process counter store
used by the OMS / event bus / HTTP server. The HTTP observability
server (B8+B9) renders EventMetrics + LifecycleManager state in
Prometheus text format.
"""

from __future__ import annotations

from brokers.common.observability.event_metrics import EventMetrics

__all__ = ["EventMetrics"]
