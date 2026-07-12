"""CLI trade spine uses build_runtime (TRANS-P5-022)."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
def test_main_defines_trade_spine_commands() -> None:
    import interface.ui.main as main_mod

    assert "place-order" in main_mod._TRADE_SPINE_CMDS
    assert "orders" in main_mod._TRADE_SPINE_CMDS


@pytest.mark.unit
def test_bootstrap_trade_runtime_delegates_to_compose() -> None:
    import interface.ui.main as main_mod

    src = inspect.getsource(main_mod._bootstrap_trade_runtime)
    assert "build_runtime" in src