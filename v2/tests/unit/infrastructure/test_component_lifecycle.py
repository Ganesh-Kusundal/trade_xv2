"""Component lifecycle state machine — valid/invalid transitions."""

from __future__ import annotations

import pytest

from infrastructure.component.base import Component, ComponentState
from shared.errors import LifecycleError


class _Probe(Component):
    """Minimal concrete component for lifecycle tests."""

    def __init__(self, component_id: str = "probe") -> None:
        super().__init__(component_id)
        self.hooks: list[str] = []

    def _on_initialize(self, config: object | None = None) -> None:
        self.hooks.append("initialize")

    def _on_start(self) -> None:
        self.hooks.append("start")

    def _on_stop(self) -> None:
        self.hooks.append("stop")

    def _on_reset(self) -> None:
        self.hooks.append("reset")


def test_starts_uninitialized() -> None:
    c = _Probe()
    assert c.state is ComponentState.UNINITIALIZED


def test_valid_happy_path() -> None:
    c = _Probe()
    c.initialize()
    assert c.state is ComponentState.INITIALIZED
    c.start()
    assert c.state is ComponentState.RUNNING
    c.stop()
    assert c.state is ComponentState.STOPPED
    c.reset()
    assert c.state is ComponentState.INITIALIZED
    assert c.hooks == ["initialize", "start", "stop", "reset"]


def test_running_to_error_via_mark_error() -> None:
    c = _Probe()
    c.initialize()
    c.start()
    c._enter_error("boom")
    assert c.state is ComponentState.ERROR


def test_invalid_start_before_initialize_raises() -> None:
    c = _Probe()
    with pytest.raises(LifecycleError):
        c.start()
    assert c.state is ComponentState.UNINITIALIZED


def test_invalid_stop_from_initialized_raises() -> None:
    c = _Probe()
    c.initialize()
    with pytest.raises(LifecycleError):
        c.stop()
    assert c.state is ComponentState.INITIALIZED


def test_invalid_reset_from_running_raises() -> None:
    c = _Probe()
    c.initialize()
    c.start()
    with pytest.raises(LifecycleError):
        c.reset()
    assert c.state is ComponentState.RUNNING


def test_double_initialize_raises() -> None:
    c = _Probe()
    c.initialize()
    with pytest.raises(LifecycleError):
        c.initialize()


def test_health_check_reports_state() -> None:
    c = _Probe()
    c.initialize()
    health = c.health_check()
    assert health.component_id == "probe"
    assert health.state is ComponentState.INITIALIZED
    assert health.healthy is True
