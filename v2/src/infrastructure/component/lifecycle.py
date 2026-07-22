"""LifecycleManager — ordered initialize/start, reverse stop."""

from __future__ import annotations

from infrastructure.component.base import Component, ComponentHealth, ComponentState
from shared.errors import LifecycleError


class LifecycleManager:
    def __init__(self) -> None:
        self._components: list[Component] = []
        self._initialized = False

    def register(self, component: Component) -> None:
        self._components.append(component)

    @property
    def components(self) -> list[Component]:
        return list(self._components)

    def initialize_all(self, config: object | None = None) -> None:
        for component in self._components:
            try:
                component.initialize(config)
            except Exception as exc:
                component._enter_error(str(exc))
                raise LifecycleError(
                    f"initialize aborted at {component.component_id}: {exc}"
                ) from exc
        self._initialized = True

    def start_all(self) -> None:
        if not self._initialized:
            raise LifecycleError("start_all requires successful initialize_all")
        if any(c.state is ComponentState.ERROR for c in self._components):
            raise LifecycleError("start_all aborted: a component is in ERROR")
        if any(c.state is not ComponentState.INITIALIZED for c in self._components):
            raise LifecycleError("start_all aborted: not all components INITIALIZED")
        for component in self._components:
            component.start()

    def stop_all(self) -> None:
        for component in reversed(self._components):
            if component.state is ComponentState.RUNNING:
                component.stop()

    def health(self) -> list[ComponentHealth]:
        return [c.health_check() for c in self._components]
