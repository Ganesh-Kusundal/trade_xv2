"""RuntimeFactory.build — paper profile wires engine + frozen PAPER environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.execution import ExecutionEngine
from config.loader import load_config
from config.schema import Environment
from runtime.factory import RuntimeFactory
from runtime.runtime import Runtime

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_build_paper_config_engine_present_environment_frozen() -> None:
    config = load_config(_CONFIG_DIR, profile="paper")
    runtime = RuntimeFactory.build(config)

    assert isinstance(runtime, Runtime)
    assert isinstance(runtime.execution_engine, ExecutionEngine)
    assert runtime.environment is Environment.PAPER
    assert runtime.risk is not None
    assert runtime.bus is not None
    assert runtime.cache is not None
    assert runtime.lifecycle is not None
    assert runtime.fill_source is not None
    assert runtime.clock is not None
    # frozen dataclass — cannot assign environment after build
    with pytest.raises(Exception):
        runtime.environment = Environment.LIVE  # type: ignore[misc]


def test_profiles_load_for_all_modes() -> None:
    expected = {
        "replay": Environment.REPLAY,
        "backtest": Environment.BACKTEST,
        "paper": Environment.PAPER,
        "live": Environment.LIVE,
    }
    for profile, env in expected.items():
        cfg = load_config(_CONFIG_DIR, profile=profile)
        assert cfg.environment is env
        rt = RuntimeFactory.build(cfg)
        assert rt.environment is env
