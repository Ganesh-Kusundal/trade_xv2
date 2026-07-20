"""TRANS-P5-022 — compose paths delegate to runtime.factory.build."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_compose_build_runtime_delegates_to_factory() -> None:
    import interface.ui.services.compose as compose_mod

    src = inspect.getsource(compose_mod.build_runtime)
    assert "build(" in src
    assert "TradingRuntimeFactory(" not in src
    assert compose_mod.build is not None


@pytest.mark.architecture
def test_compose_build_for_api_delegates_to_factory() -> None:
    import runtime.api_compose as api_compose

    src = inspect.getsource(api_compose.build_for_api)
    assert "build(" in src
    assert "TradingRuntimeFactory(" not in src
