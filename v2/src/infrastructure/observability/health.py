"""Component health tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComponentHealth:
    component_id: str
    state: str
    metrics: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None


class HealthRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, ComponentHealth] = {}

    def update(self, health: ComponentHealth) -> None:
        self._by_id[health.component_id] = health

    def get(self, component_id: str) -> ComponentHealth | None:
        return self._by_id.get(component_id)

    def all(self) -> list[ComponentHealth]:
        return list(self._by_id.values())
