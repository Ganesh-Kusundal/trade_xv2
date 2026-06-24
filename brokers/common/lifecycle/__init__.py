"""Shim — use :mod:`infrastructure.lifecycle`."""

from infrastructure.lifecycle import (
    HealthState,
    HealthStatus,
    LifecycleManager,
    ManagedService,
    build_health,
    now_monotonic,
)

__all__ = [
    "HealthState",
    "HealthStatus",
    "LifecycleManager",
    "ManagedService",
    "build_health",
    "now_monotonic",
]
