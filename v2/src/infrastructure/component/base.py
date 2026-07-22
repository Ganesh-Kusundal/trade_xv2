"""Component ABC and lifecycle state machine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from shared.errors import LifecycleError


class ComponentState(Enum):
    UNINITIALIZED = auto()
    INITIALIZED = auto()
    RUNNING = auto()
    STOPPED = auto()
    ERROR = auto()


# Valid transitions: from -> frozenset of allowed next states
_TRANSITIONS: dict[ComponentState, frozenset[ComponentState]] = {
    ComponentState.UNINITIALIZED: frozenset({ComponentState.INITIALIZED, ComponentState.ERROR}),
    ComponentState.INITIALIZED: frozenset({ComponentState.RUNNING, ComponentState.ERROR}),
    ComponentState.RUNNING: frozenset({ComponentState.STOPPED, ComponentState.ERROR}),
    ComponentState.STOPPED: frozenset({ComponentState.INITIALIZED, ComponentState.ERROR}),
    ComponentState.ERROR: frozenset(),
}


@dataclass(frozen=True)
class ComponentHealth:
    component_id: str
    state: ComponentState
    healthy: bool
    detail: str = ""


class Component(ABC):
    """Framework component with enforced lifecycle state machine."""

    def __init__(self, component_id: str) -> None:
        self.component_id = component_id
        self.state = ComponentState.UNINITIALIZED

    def initialize(self, config: Any = None) -> None:
        self._transition(ComponentState.INITIALIZED)
        try:
            self._on_initialize(config)
        except Exception:
            self.state = ComponentState.ERROR
            raise

    def start(self) -> None:
        self._transition(ComponentState.RUNNING)
        try:
            self._on_start()
        except Exception:
            self.state = ComponentState.ERROR
            raise

    def stop(self) -> None:
        self._transition(ComponentState.STOPPED)
        try:
            self._on_stop()
        except Exception:
            self.state = ComponentState.ERROR
            raise

    def reset(self) -> None:
        self._transition(ComponentState.INITIALIZED)
        try:
            self._on_reset()
        except Exception:
            self.state = ComponentState.ERROR
            raise

    def health_check(self) -> ComponentHealth:
        return ComponentHealth(
            component_id=self.component_id,
            state=self.state,
            healthy=self.state
            in {
                ComponentState.INITIALIZED,
                ComponentState.RUNNING,
                ComponentState.STOPPED,
            },
        )

    def _enter_error(self, detail: str = "") -> None:
        """Enter ERROR from any non-ERROR state (operator intervention required)."""
        if self.state is not ComponentState.ERROR:
            self.state = ComponentState.ERROR

    def _transition(self, target: ComponentState) -> None:
        allowed = _TRANSITIONS.get(self.state, frozenset())
        if target not in allowed:
            raise LifecycleError(
                f"{self.component_id}: {self.state.name} → {target.name} is invalid"
            )
        self.state = target

    @abstractmethod
    def _on_initialize(self, config: Any = None) -> None: ...

    @abstractmethod
    def _on_start(self) -> None: ...

    @abstractmethod
    def _on_stop(self) -> None: ...

    @abstractmethod
    def _on_reset(self) -> None: ...
