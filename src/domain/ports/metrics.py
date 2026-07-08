"""Metrics port — application-layer boundary for metrics collection."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Re-export the singleton so broker code can import from domain.
from infrastructure.metrics.registry import metrics_registry  # noqa: E402


@runtime_checkable
class MetricsRegistryPort(Protocol):
    """Protocol for metrics collection (counter, gauge, histogram)."""

    def counter(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Any: ...

    def gauge(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Any: ...

    def histogram(
        self, name: str, description: str = "", labels: dict[str, str] | None = None, buckets: list[float] | None = None
    ) -> Any: ...

    def snapshot(self) -> dict[str, Any]: ...
