"""Lifecycle port — application-layer boundary for managed services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.lifecycle_health import HealthStatus


@runtime_checkable
class ManagedServicePort(Protocol):
    """Protocol for a long-running service participating in the lifecycle."""

    name: str

    def start(self) -> None: ...

    def stop(self, timeout_seconds: float = 5.0) -> None: ...

    def health(self) -> HealthStatus: ...
