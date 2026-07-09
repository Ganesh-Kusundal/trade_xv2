"""ENG-012: ResearchMode pure_sim vs parity."""

from __future__ import annotations

import pytest

from analytics.backtest.engine import BacktestEngine, ResearchMode


def test_default_mode_is_pure_sim():
    eng = BacktestEngine()
    assert eng.mode is ResearchMode.PURE_SIM


def test_parity_requires_oms_or_context():
    with pytest.raises(ValueError, match="PARITY"):
        BacktestEngine(mode=ResearchMode.PARITY)


def test_parity_accepts_oms_adapter():
    eng = BacktestEngine(mode="parity", oms_adapter=object())
    assert eng.mode is ResearchMode.PARITY
