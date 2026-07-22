"""LifecycleManager — start order, stop reverse, abort on init failure."""

from __future__ import annotations

import pytest

from infrastructure.component.base import Component, ComponentState
from infrastructure.component.lifecycle import LifecycleManager
from shared.errors import LifecycleError


class _Ordered(Component):
    def __init__(self, component_id: str, log: list[str], *, fail_init: bool = False) -> None:
        super().__init__(component_id)
        self._log = log
        self._fail_init = fail_init

    def _on_initialize(self, config: object | None = None) -> None:
        if self._fail_init:
            raise RuntimeError(f"{self.component_id} init failed")
        self._log.append(f"init:{self.component_id}")

    def _on_start(self) -> None:
        self._log.append(f"start:{self.component_id}")

    def _on_stop(self) -> None:
        self._log.append(f"stop:{self.component_id}")

    def _on_reset(self) -> None:
        self._log.append(f"reset:{self.component_id}")


def test_start_all_preserves_registration_order() -> None:
    log: list[str] = []
    lm = LifecycleManager()
    lm.register(_Ordered("a", log))
    lm.register(_Ordered("b", log))
    lm.register(_Ordered("c", log))
    lm.initialize_all()
    lm.start_all()
    assert log == [
        "init:a",
        "init:b",
        "init:c",
        "start:a",
        "start:b",
        "start:c",
    ]
    assert all(c.state is ComponentState.RUNNING for c in lm.components)


def test_stop_all_reverses_order() -> None:
    log: list[str] = []
    lm = LifecycleManager()
    lm.register(_Ordered("a", log))
    lm.register(_Ordered("b", log))
    lm.register(_Ordered("c", log))
    lm.initialize_all()
    lm.start_all()
    log.clear()
    lm.stop_all()
    assert log == ["stop:c", "stop:b", "stop:a"]
    assert all(c.state is ComponentState.STOPPED for c in lm.components)


def test_initialize_all_aborts_on_failure_no_partial_running() -> None:
    log: list[str] = []
    lm = LifecycleManager()
    a = _Ordered("a", log)
    b = _Ordered("b", log, fail_init=True)
    c = _Ordered("c", log)
    lm.register(a)
    lm.register(b)
    lm.register(c)
    with pytest.raises(LifecycleError, match="b"):
        lm.initialize_all()
    assert a.state is ComponentState.INITIALIZED
    assert b.state is ComponentState.ERROR
    assert c.state is ComponentState.UNINITIALIZED
    with pytest.raises(LifecycleError):
        lm.start_all()
    assert a.state is not ComponentState.RUNNING
    assert c.state is not ComponentState.RUNNING


def test_health_aggregates_component_health() -> None:
    log: list[str] = []
    lm = LifecycleManager()
    lm.register(_Ordered("x", log))
    lm.initialize_all()
    reports = lm.health()
    assert len(reports) == 1
    assert reports[0].component_id == "x"
    assert reports[0].healthy is True
