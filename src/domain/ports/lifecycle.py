"""Lifecycle ports — application-layer boundary for managed services."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from domain.lifecycle_health import HealthStatus


@runtime_checkable
class ManagedServicePort(Protocol):
    """Protocol for a long-running service participating in the lifecycle."""

    name: str

    def start(self) -> None: ...

    def stop(self, timeout_seconds: float = 5.0) -> None: ...

    def health(self) -> HealthStatus: ...


@runtime_checkable
class LifecycleManagerPort(Protocol):
    """Application boundary for the lifecycle manager.

    The OMS depends on this port (register/start/stop services); the
    concrete ``LifecycleManager`` is injected by a composition root
    (cli / api / brokers.common), never constructed inside ``application``.
    """

    def register(self, service: ManagedServicePort) -> None: ...

    def unregister(self, name: str) -> None: ...

    def get(self, name: str) -> ManagedServicePort | None: ...

    def service_names(self) -> list[str]: ...

    def start(self, name: str) -> None: ...

    def stop(self, name: str, timeout_seconds: float | None = None) -> None: ...

    def start_all(self) -> None: ...

    def stop_all(self) -> None: ...

    def health_snapshot(self) -> dict[str, dict[str, Any]]: ...

    def last_health(self, name: str) -> HealthStatus | None: ...
