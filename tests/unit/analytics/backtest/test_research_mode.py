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


def test_facade_backtest_defaults_to_pure_sim():
    from analytics.facade import Analytics

    engine = Analytics().backtest()
    assert engine.mode is ResearchMode.PURE_SIM


def test_facade_backtest_forwards_parity_mode_and_context():
    """Analytics.backtest(mode=PARITY, trading_context=...) reaches BacktestEngine."""
    from analytics.facade import Analytics

    engine = Analytics().backtest(mode=ResearchMode.PARITY, trading_context=object())
    assert engine.mode is ResearchMode.PARITY


def test_run_backtest_cli_builds_real_trading_context_for_parity():
    """run_backtest.py's --parity path composes a real, broker-free TradingContext."""
    from application.oms.context import TradingContext
    from analytics.backtest.run_backtest import _build_parity_context

    ctx = _build_parity_context(initial_capital=100_000)
    assert isinstance(ctx, TradingContext)
    assert ctx.risk_manager is not None
    assert ctx.order_manager is not None


def test_run_backtest_cli_parity_without_symbol_raises():
    """--parity without --symbol is rejected (mirrors ReplayEngine TypeError contract)."""
    from analytics.backtest.run_backtest import main
    import sys

    old_argv = sys.argv
    try:
        sys.argv = ["run_backtest", "--parity", "--scan"]
        with pytest.raises(SystemExit):
            main()
    finally:
        sys.argv = old_argv


def test_optimizer_accepts_optional_trading_context_for_parity_confirmation():
    """optimize_grid keeps PURE_SIM for the grid; optional trading_context re-runs winner in PARITY."""
    import pandas as pd

    from analytics.backtest.optimizer import ParamGrid, optimize_grid
    from tests.conftest import build_test_trading_context

    ts = pd.date_range("2026-01-02 09:15", periods=120, freq="1min")
    price = 100 + pd.Series(range(120)).astype(float) * 0.05
    data = pd.DataFrame(
        {
            "timestamp": ts,
            "open": price,
            "high": price + 0.3,
            "low": price - 0.3,
            "close": price,
            "volume": 5000,
        }
    )
    ctx = build_test_trading_context(replay_events=False)
    result = optimize_grid(
        data,
        symbol="OPT",
        param_grids=[ParamGrid("rsi_period", [7, 14])],
        warmup_bars=20,
        trading_context=ctx,
    )
    assert result.best_params
    parity_rows = [r for r in result.results if r.get("parity_confirmation")]
    assert len(parity_rows) == 1
