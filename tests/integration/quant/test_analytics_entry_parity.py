"""Analytics entry-point PARITY equivalence (plan step 6).

Exercises .replay(), .backtest(mode=PARITY), and .paper() against real
TradingContexts (no mocks) on the same OHLCV and asserts identical
signal/trade counts + direction, with a float tolerance on equity.
"""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.backtest.engine import BacktestEngine, ResearchMode
from analytics.backtest.models import BacktestConfig
from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import PaperConfig
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from tests.conftest import build_test_trading_context

EQUITY_TOLERANCE = 1e-6


def _ohlcv(rows: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2026-01-02 09:15", periods=rows, freq="1min")
    price = 100 + pd.Series(range(rows)).astype(float) * 0.1
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 10000,
        }
    )


class AlwaysBuyStrategy:
    name = "always_buy"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.BUY,
            confidence=0.9,
            strategy=self.name,
        )


def _norm_side(side: object) -> str:
    return str(side).upper().split(".")[-1]


def _trade_fingerprint(trade) -> tuple:
    return (
        trade.symbol,
        _norm_side(trade.side),
        int(trade.quantity),
        trade.entry_time,
        trade.exit_time,
    )


@pytest.mark.paper_replay_parity
def test_analytics_entry_points_parity_equivalence() -> None:
    """replay == backtest(PARITY) == paper for same data + real TradingContext."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])
    df = _ohlcv()
    symbol = "PARITY"

    common_kwargs = dict(
        initial_capital=100_000,
        warmup_bars=5,
        max_position_pct=100.0,
        slippage_pct=0.0,
    )

    replay = ReplayEngine(
        pipeline,
        strategy,
        ReplayConfig(**common_kwargs),
        trading_context=build_test_trading_context(replay_events=False),
    )
    backtest = BacktestEngine(
        pipeline,
        strategy,
        BacktestConfig(**common_kwargs),
        mode=ResearchMode.PARITY,
        trading_context=build_test_trading_context(replay_events=False),
    )
    paper = PaperTradingEngine(
        pipeline,
        strategy,
        PaperConfig(**common_kwargs),
        trading_context=build_test_trading_context(replay_events=False),
    )

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    # Backtest wraps ReplayResult; unwrap for comparison.
    bt_replay = backtest_result.replay

    assert replay_result.bars_processed == bt_replay.bars_processed == paper_result.bars_processed
    assert replay_result.signals_generated == bt_replay.signals_generated == paper_result.signals_generated

    r_trades = replay_result.session.trades
    b_trades = bt_replay.session.trades
    p_trades = paper_result.session.trades

    assert len(r_trades) == len(b_trades) == len(p_trades)
    assert [_trade_fingerprint(t) for t in r_trades] == [
        _trade_fingerprint(t) for t in b_trades
    ]
    assert [_trade_fingerprint(t) for t in r_trades] == [
        _trade_fingerprint(t) for t in p_trades
    ]

    # Equity curve: same length, final equity within float tolerance.
    r_eq = replay_result.session.equity_curve
    b_eq = bt_replay.session.equity_curve
    p_eq = paper_result.session.equity_curve
    assert len(r_eq) == len(b_eq) == len(p_eq)
    assert abs(r_eq[-1][1] - b_eq[-1][1]) < EQUITY_TOLERANCE
    assert abs(r_eq[-1][1] - p_eq[-1][1]) < EQUITY_TOLERANCE
