"""Thin service registry for the composition root (Context 6).

ponytail: dict-backed name→instance map; upgrade path is typed slots on Runtime.
"""

from __future__ import annotations

from typing import Any


class ServiceRegistry:
    """Name → service map for lifecycle-owned kernel services."""

    __slots__ = ("_services",)

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        if not name:
            raise ValueError("service name required")
        self._services[name] = service

    def get(self, name: str) -> Any | None:
        return self._services.get(name)

    def require(self, name: str) -> Any:
        svc = self._services.get(name)
        if svc is None:
            raise KeyError(f"service not registered: {name}")
        return svc

    def names(self) -> frozenset[str]:
        return frozenset(self._services)

    def as_dict(self) -> dict[str, str]:
        return {k: type(v).__name__ for k, v in self._services.items()}
