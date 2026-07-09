"""AN-011 — Backtest consumes Instrument.history (session product path).

Proves research stack accepts the same HistoricalSeries → DataFrame shape
produced by tradex.connect paper instruments (no broker imports in test body).
"""

from __future__ import annotations

import tradex
from analytics.backtest.engine import BacktestConfig, BacktestEngine, ResearchMode
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.strategy.pipeline import StrategyPipeline
from analytics.strategy.registry import StrategyRegistry
from domain.candles.historical import HistoricalSeries


def test_an011_session_history_is_historical_series() -> None:
    session = tradex.connect("paper")
    try:
        series = session.universe.equity("RELIANCE").history(timeframe="1D", days=40)
        assert isinstance(series, HistoricalSeries)
        assert series.bar_count == 40
        df = series.to_dataframe()
        assert {"timestamp", "open", "high", "low", "close", "volume"}.issubset(df.columns)
    finally:
        session.close()


def test_an011_backtest_pure_sim_on_session_history() -> None:
    session = tradex.connect("paper")
    try:
        series = session.universe.equity("RELIANCE").history(timeframe="1D", days=80)
        df = series.to_dataframe().drop(
            columns=["symbol", "exchange", "timeframe", "oi"],
            errors="ignore",
        )
    finally:
        session.close()

    StrategyRegistry.discover("analytics.strategy.builtins")
    strat = StrategyRegistry.create("momentum")
    engine = BacktestEngine(
        FeaturePipeline(),
        StrategyPipeline(strategies=[strat]),
        BacktestConfig(initial_capital=100_000, warmup_bars=5),
        mode=ResearchMode.PURE_SIM,
    )
    assert engine.mode is ResearchMode.PURE_SIM
    result = engine.run(df, symbol="RELIANCE")
    assert result is not None
    assert result.replay.bars_processed == 80
    assert result.metrics is not None


def test_an011_parity_mode_requires_oms() -> None:
    StrategyRegistry.discover("analytics.strategy.builtins")
    strat = StrategyRegistry.create("momentum")
    try:
        BacktestEngine(
            FeaturePipeline(),
            StrategyPipeline(strategies=[strat]),
            mode=ResearchMode.PARITY,
        )
        raised = False
    except ValueError as exc:
        raised = True
        assert "PARITY" in str(exc) or "ENG-012" in str(exc)
    assert raised is True
