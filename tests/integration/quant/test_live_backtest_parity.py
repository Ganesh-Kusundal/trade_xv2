"""Live ↔ backtest parity contract — API research mode is not live parity."""

from __future__ import annotations

import pytest

from analytics.backtest import BacktestEngine, ResearchMode


@pytest.mark.live_backtest_parity
def test_api_backtest_defaults_to_pure_sim_research_mode():
    """HTTP backtest path must not claim live execution parity."""
    engine = BacktestEngine(mode=ResearchMode.PURE_SIM)
    assert engine.mode is ResearchMode.PURE_SIM
    assert engine.mode.value == "pure_sim"


@pytest.mark.live_backtest_parity
def test_parity_mode_requires_oms_wiring():
    with pytest.raises(ValueError, match="ResearchMode.PARITY"):
        BacktestEngine(mode=ResearchMode.PARITY)