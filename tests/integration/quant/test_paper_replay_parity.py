"""Paper vs replay execution parity (REF-9)."""

from __future__ import annotations
from tests.conftest import build_test_trading_context

import pandas as pd
import pytest

from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import PaperConfig
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from application.oms.factory import create_trading_context
from runtime.wire_runtime_hooks import wire_runtime_hooks


def _norm_side(side: object) -> str:
    return str(side).upper().split(".")[-1]


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


@pytest.fixture
def trading_context():
    # Composition-root wiring: register the real OMS backtest factory so the
    # replay engine routes through the shared OMS kernel (zero-parity), not SIM.
    wire_runtime_hooks()
    return build_test_trading_context(replay_events=False)


def test_paper_replay_parity_same_trades(trading_context) -> None:
    """Paper and replay must produce identical trade counts and PnL on same OHLCV."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])
    df = _ohlcv()
    symbol = "TEST"

    replay_cfg = ReplayConfig(
        initial_capital=100_000, warmup_bars=5, max_position_pct=100.0, slippage_pct=0.0
    )
    paper_cfg = PaperConfig(
        initial_capital=100_000, warmup_bars=5, max_position_pct=100.0, slippage_pct=0.0
    )

    replay = ReplayEngine(
        pipeline,
        strategy,
        replay_cfg,
        trading_context=trading_context,
    )
    paper = PaperTradingEngine(
        pipeline,
        strategy,
        paper_cfg,
        trading_context=build_test_trading_context(replay_events=False),
    )

    replay_result = replay.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    assert replay_result.bars_processed == paper_result.bars_processed
    assert len(replay_result.session.trades) == len(paper_result.session.trades)
    assert replay_result.session.total_trades == paper_result.session.total_trades

    if replay_result.session.trades:
        r_trade = replay_result.session.trades[0]
        p_trade = paper_result.session.trades[0]
        assert r_trade.symbol == p_trade.symbol
        assert _norm_side(r_trade.side) == _norm_side(p_trade.side)
        assert r_trade.quantity == p_trade.quantity
        assert r_trade.entry_time == p_trade.entry_time
        assert r_trade.exit_time == p_trade.exit_time
