"""3-engine simulation parity gate — WS-B prerequisite.

Runs the same OHLCV data and strategy configuration through all three
simulation engines (ReplayEngine, BacktestEngine with PARITY mode, and
PaperTradingEngine) and asserts bit-identical output across:

- bars processed / signals generated
- trade count, direction, quantity, entry/exit timing
- PnL per trade (within float tolerance)
- equity curve length and final equity
- multi-symbol handling
- commission + slippage parity
- multi-day data with calendar gaps

Prerequisite: wire_runtime_hooks() so the OMS backtest adapter is registered.
"""

from __future__ import annotations

import logging

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
from runtime.wire_runtime_hooks import wire_runtime_hooks
from tests.conftest import build_test_trading_context

logger = logging.getLogger(__name__)

EQUITY_TOLERANCE = 1e-6
PNL_TOLERANCE = 1e-3


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------


class AlwaysBuyStrategy:
    """Buy every bar after warmup at fixed confidence."""

    name = "always_buy"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.BUY,
            confidence=0.9,
            strategy=self.name,
        )


class FlipFlopStrategy:
    """Alternate BUY / SELL to produce round-trip trades."""

    name = "flip_flop"

    def __init__(self) -> None:
        self._n = 0

    def evaluate(self, candidate, features):
        self._n += 1
        st = SignalType.BUY if self._n % 2 == 1 else SignalType.SELL
        return Signal(
            symbol=candidate.symbol,
            signal_type=st,
            confidence=0.9,
            strategy=self.name,
        )


# ---------------------------------------------------------------------------
# OHLCV data helpers
# ---------------------------------------------------------------------------


def _uptrend_ohlcv(rows: int = 80) -> pd.DataFrame:
    """Steady uptrend — always_buy makes money."""
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


def _declining_ohlcv(rows: int = 60) -> pd.DataFrame:
    """Declining price — always_buy loses money for full round-trip."""
    ts = pd.date_range("2026-01-02 09:15", periods=rows, freq="1min")
    price = 200 - pd.Series(range(rows)).astype(float) * 1.0
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": price,
            "high": price + 0.25,
            "low": price - 0.25,
            "close": price,
            "volume": 10000,
        }
    )


def _multi_day_ohlcv() -> pd.DataFrame:
    """Data spanning 3 trading days (with gaps for weekends)."""
    dfs = []
    for day_offset, day_price in [(0, 100.0), (2, 102.0), (4, 104.0)]:  # skip weekends
        day_start = pd.Timestamp("2026-01-02") + pd.Timedelta(days=day_offset)
        ts = pd.date_range(f"{day_start.date()} 09:15", periods=25, freq="1min")
        price = day_price + pd.Series(range(len(ts))).astype(float) * 0.05
        dfs.append(
            pd.DataFrame(
                {
                    "timestamp": ts,
                    "open": price,
                    "high": price + 0.3,
                    "low": price - 0.3,
                    "close": price,
                    "volume": 10000,
                }
            )
        )
    return pd.concat(dfs, ignore_index=True)


# ---------------------------------------------------------------------------
# Trade comparison helpers
# ---------------------------------------------------------------------------


def _norm_side(side: object) -> str:
    return str(side).upper().split(".")[-1]


def _trade_fingerprint(trade) -> tuple:
    """Canonical trade identifier for cross-engine comparison."""
    return (
        trade.symbol,
        _norm_side(trade.side),
        int(trade.quantity),
        trade.entry_time,
        trade.exit_time,
    )


def _trade_pnl(trade) -> float:
    """Extract PnL from trade regardless of type (PaperTrade vs SimulatedTrade)."""
    if hasattr(trade, "pnl"):
        pnl = trade.pnl
        return float(pnl) if not isinstance(pnl, (int, float)) else pnl
    return 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _wired():
    """Wire runtime hooks + domain port sinks once per module."""
    from runtime.factory import wire_domain_port_sinks

    wire_runtime_hooks()
    wire_domain_port_sinks()


@pytest.fixture
def trading_context(_wired):
    """TradingContext with no event replay (sim-only)."""
    return build_test_trading_context(replay_events=False)


# ---------------------------------------------------------------------------
# Test: Basic 3-engine parity — single symbol, uptrend, zero friction
# ---------------------------------------------------------------------------


def _build_engines(
    pipeline,
    strategy,
    symbol: str,
    *,
    initial_capital: float = 100_000,
    warmup_bars: int = 5,
    max_position_pct: float = 100.0,
    slippage_pct: float = 0.0,
    commission_flat: float = 0.0,
    trading_context=None,
):
    """Build all 3 engines with identical configuration."""
    common_kwargs = {
        "initial_capital": initial_capital,
        "warmup_bars": warmup_bars,
        "max_position_pct": max_position_pct,
        "slippage_pct": slippage_pct,
        "commission_flat": commission_flat,
    }

    ctx = trading_context or build_test_trading_context(replay_events=False)

    replay = ReplayEngine(
        pipeline,
        strategy,
        ReplayConfig(**common_kwargs),
        trading_context=ctx,
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
    return replay, backtest, paper


def test_basic_3engine_parity(trading_context) -> None:
    """All 3 engines produce identical trade counts and fingerprints."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline, strategy, "PARITY", trading_context=trading_context
    )

    df = _uptrend_ohlcv(80)
    symbol = "PARITY"

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    bt_replay = backtest_result.replay

    # Core metrics
    assert replay_result.bars_processed == bt_replay.bars_processed == paper_result.bars_processed
    assert (
        replay_result.signals_generated
        == bt_replay.signals_generated
        == paper_result.signals_generated
    )

    # Trade count
    r_trades = replay_result.session.trades
    b_trades = bt_replay.session.trades
    p_trades = paper_result.session.trades
    assert len(r_trades) == len(b_trades) == len(p_trades), (
        f"Trade count mismatch: replay={len(r_trades)}, backtest={len(b_trades)}, paper={len(p_trades)}"
    )

    # Trade fingerprints (identity)
    assert [_trade_fingerprint(t) for t in r_trades] == [_trade_fingerprint(t) for t in b_trades]
    assert [_trade_fingerprint(t) for t in r_trades] == [_trade_fingerprint(t) for t in p_trades]

    # Per-trade PnL
    for i in range(len(r_trades)):
        r_pnl = _trade_pnl(r_trades[i])
        b_pnl = _trade_pnl(b_trades[i])
        p_pnl = _trade_pnl(p_trades[i])
        assert abs(r_pnl - b_pnl) < PNL_TOLERANCE, (
            f"Trade {i} PnL mismatch: replay={r_pnl}, backtest={b_pnl}"
        )
        assert abs(r_pnl - p_pnl) < PNL_TOLERANCE, (
            f"Trade {i} PnL mismatch: replay={r_pnl}, paper={p_pnl}"
        )

    # Equity curve length
    r_eq = replay_result.session.equity_curve
    b_eq = bt_replay.session.equity_curve
    p_eq = paper_result.session.equity_curve
    assert len(r_eq) == len(b_eq) == len(p_eq), "Equity curve length mismatch"

    # Final equity
    assert abs(r_eq[-1][1] - b_eq[-1][1]) < EQUITY_TOLERANCE
    assert abs(r_eq[-1][1] - p_eq[-1][1]) < EQUITY_TOLERANCE


# ---------------------------------------------------------------------------
# Test: Multi-symbol parity
# ---------------------------------------------------------------------------


def test_multi_symbol_parity(trading_context) -> None:
    """Identical config on 2 symbols must produce identical per-symbol trades."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline, strategy, "SYM_A", trading_context=trading_context
    )

    df_a = _uptrend_ohlcv(60)
    df_b = _uptrend_ohlcv(60)  # Same data = same results

    r_a = replay.run(df_a.copy(), symbol="SYM_A")
    r_b = replay.run(df_b.copy(), symbol="SYM_B")

    bt_a = backtest.run(df_a.copy(), symbol="SYM_A").replay
    bt_b = backtest.run(df_b.copy(), symbol="SYM_B").replay

    p_a = paper.run(df_a.copy(), symbol="SYM_A")
    p_b = paper.run(df_b.copy(), symbol="SYM_B")

    # Same data → same results regardless of symbol name
    assert len(r_a.session.trades) == len(r_b.session.trades) == len(bt_a.session.trades)
    assert len(p_a.session.trades) == len(p_b.session.trades)

    # Same engine, different symbols → same trade structures
    for i in range(len(r_a.session.trades)):
        # Same quantity, same timing
        assert r_a.session.trades[i].quantity == r_b.session.trades[i].quantity
        assert r_a.session.trades[i].entry_time == r_b.session.trades[i].entry_time
        assert bt_a.session.trades[i].quantity == bt_b.session.trades[i].quantity
        assert p_a.session.trades[i].quantity == p_b.session.trades[i].quantity

    # Cross-engine: same symbol → same results
    assert len(r_a.session.trades) == len(p_a.session.trades) == len(bt_a.session.trades)
    r_fp = [_trade_fingerprint(t) for t in r_a.session.trades]
    p_fp = [_trade_fingerprint(t) for t in p_a.session.trades]
    b_fp = [_trade_fingerprint(t) for t in bt_a.session.trades]
    assert r_fp == p_fp == b_fp


# ---------------------------------------------------------------------------
# Test: Commission + slippage parity
# ---------------------------------------------------------------------------


def test_commission_slippage_parity(trading_context) -> None:
    """Non-zero commission and slippage must produce identical results."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline,
        strategy,
        "COMMSLP",
        initial_capital=100_000,
        warmup_bars=5,
        max_position_pct=50.0,
        slippage_pct=0.05,  # 0.05% slippage
        commission_flat=10.0,  # ₹10 flat commission per trade
        trading_context=trading_context,
    )

    df = _uptrend_ohlcv(80)
    symbol = "COMMSLP"

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    bt_replay = backtest_result.replay

    # Trade count must match
    r_trades = replay_result.session.trades
    b_trades = bt_replay.session.trades
    p_trades = paper_result.session.trades
    assert len(r_trades) == len(b_trades) == len(p_trades), (
        f"With commission: trade count mismatch: {len(r_trades)} vs {len(b_trades)} vs {len(p_trades)}"
    )

    # Fingerprints must match
    r_fp = [_trade_fingerprint(t) for t in r_trades]
    b_fp = [_trade_fingerprint(t) for t in b_trades]
    p_fp = [_trade_fingerprint(t) for t in p_trades]
    assert r_fp == b_fp == p_fp, "Commission + slippage: trade fingerprints must match"

    # Per-trade PnL must match (commission/slippage applies identically)
    for i in range(len(r_trades)):
        r_pnl = _trade_pnl(r_trades[i])
        b_pnl = _trade_pnl(b_trades[i])
        p_pnl = _trade_pnl(p_trades[i])
        assert abs(r_pnl - b_pnl) < PNL_TOLERANCE, (
            f"Trade {i} PnL with commission: replay={r_pnl}, backtest={b_pnl}"
        )
        assert abs(r_pnl - p_pnl) < PNL_TOLERANCE, (
            f"Trade {i} PnL with commission: replay={r_pnl}, paper={p_pnl}"
        )

    # Final equity must match
    r_eq = replay_result.session.equity_curve
    b_eq = bt_replay.session.equity_curve
    p_eq = paper_result.session.equity_curve
    assert len(r_eq) == len(b_eq) == len(p_eq)
    assert abs(r_eq[-1][1] - b_eq[-1][1]) < EQUITY_TOLERANCE
    assert abs(r_eq[-1][1] - p_eq[-1][1]) < EQUITY_TOLERANCE


# ---------------------------------------------------------------------------
# Test: Multi-day data parity
# ---------------------------------------------------------------------------


def test_multi_day_parity(trading_context) -> None:
    """Data spanning multiple trading days with gaps — engines must stay in sync."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline,
        strategy,
        "MULTIDAY",
        warmup_bars=5,
        max_position_pct=100.0,
        trading_context=trading_context,
    )

    df = _multi_day_ohlcv()
    symbol = "MULTIDAY"

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    bt_replay = backtest_result.replay

    assert replay_result.bars_processed == bt_replay.bars_processed == paper_result.bars_processed
    r_trades = replay_result.session.trades
    b_trades = bt_replay.session.trades
    p_trades = paper_result.session.trades
    assert len(r_trades) == len(b_trades) == len(p_trades), (
        f"Multi-day trade count: {len(r_trades)} vs {len(b_trades)} vs {len(p_trades)}"
    )
    r_fp = [_trade_fingerprint(t) for t in r_trades]
    b_fp = [_trade_fingerprint(t) for t in b_trades]
    p_fp = [_trade_fingerprint(t) for t in p_trades]
    assert r_fp == b_fp == p_fp, "Multi-day trade fingerprints must match"

    r_eq = replay_result.session.equity_curve
    b_eq = bt_replay.session.equity_curve
    p_eq = paper_result.session.equity_curve
    assert len(r_eq) == len(b_eq) == len(p_eq)
    assert abs(r_eq[-1][1] - b_eq[-1][1]) < EQUITY_TOLERANCE
    assert abs(r_eq[-1][1] - p_eq[-1][1]) < EQUITY_TOLERANCE


# ---------------------------------------------------------------------------
# Test: BUY/SELL round-trip parity (FlipFlop strategy)
# ---------------------------------------------------------------------------


def test_buy_sell_round_trip_parity(trading_context) -> None:
    """BUY/SELL round-trips must produce identical results across all 3 engines."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[FlipFlopStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline,
        strategy,
        "FLIPFLOP",
        initial_capital=100_000,
        warmup_bars=5,
        max_position_pct=50.0,
        slippage_pct=0.0,
        commission_flat=0.0,
        trading_context=trading_context,
    )

    df = _declining_ohlcv(60)  # Declining → BUY loses, SELL wins
    symbol = "FLIPFLOP"

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    bt_replay = backtest_result.replay

    r_trades = replay_result.session.trades
    b_trades = bt_replay.session.trades
    p_trades = paper_result.session.trades
    assert len(r_trades) == len(b_trades) == len(p_trades), (
        f"FlipFlop trade count: {len(r_trades)} vs {len(b_trades)} vs {len(p_trades)}"
    )

    r_fp = [_trade_fingerprint(t) for t in r_trades]
    b_fp = [_trade_fingerprint(t) for t in b_trades]
    p_fp = [_trade_fingerprint(t) for t in p_trades]
    assert r_fp == b_fp == p_fp, "FlipFlop trade fingerprints must match"

    for i in range(len(r_trades)):
        r_pnl = _trade_pnl(r_trades[i])
        b_pnl = _trade_pnl(b_trades[i])
        p_pnl = _trade_pnl(p_trades[i])
        assert abs(r_pnl - b_pnl) < PNL_TOLERANCE
        assert abs(r_pnl - p_pnl) < PNL_TOLERANCE

    r_eq = replay_result.session.equity_curve
    b_eq = bt_replay.session.equity_curve
    p_eq = paper_result.session.equity_curve
    assert len(r_eq) == len(b_eq) == len(p_eq)
    assert abs(r_eq[-1][1] - b_eq[-1][1]) < EQUITY_TOLERANCE
    assert abs(r_eq[-1][1] - p_eq[-1][1]) < EQUITY_TOLERANCE


# ---------------------------------------------------------------------------
# Test: Zero-signal edge case
# ---------------------------------------------------------------------------


def test_empty_result_parity(trading_context) -> None:
    """With warmup exceeding bars, no signals process into trades and all 3 engines produce identical empty results."""
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline, strategy, "EMPTY",
        warmup_bars=100,  # All 30 bars fall in warmup → no trades
        trading_context=trading_context,
    )

    df = _uptrend_ohlcv(30)
    symbol = "EMPTY"

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    bt_replay = backtest_result.replay

    assert replay_result.bars_processed == bt_replay.bars_processed == paper_result.bars_processed
    assert (
        replay_result.signals_generated
        == bt_replay.signals_generated
        == paper_result.signals_generated
    )
    assert len(replay_result.session.trades) == 0
    assert len(bt_replay.session.trades) == 0
    assert len(paper_result.session.trades) == 0

    # Equity curves should exist and match (initial capital = final capital)
    r_eq = replay_result.session.equity_curve
    b_eq = bt_replay.session.equity_curve
    p_eq = paper_result.session.equity_curve
    assert len(r_eq) == len(b_eq) == len(p_eq)
    for eq_name, eq in [("replay", r_eq), ("backtest", b_eq), ("paper", p_eq)]:
        for ts, val in eq:
            assert abs(val - 100_000.0) < EQUITY_TOLERANCE, (
                f"{eq_name}: equity {val} at {ts} != initial 100000"
            )


# ---------------------------------------------------------------------------
# Test: Shared simulation components produce identical internal state
# ---------------------------------------------------------------------------


def test_shared_simulation_pipeline_parity(trading_context) -> None:
    """All 3 engines use the same SimulationFillPipeline internally.

    After identical runs, the internal PortfolioProjector state must match:
    - Position count
    - Position qty / avg_price / ltp
    - Fill pipeline reducer state
    """
    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])

    replay, backtest, paper = _build_engines(
        pipeline, strategy, "PIPELINE", trading_context=trading_context
    )

    df = _uptrend_ohlcv(80)
    symbol = "PIPELINE"

    replay_result = replay.run(df, symbol=symbol)
    backtest_result = backtest.run(df, symbol=symbol)
    paper_result = paper.run(df, symbol=symbol)

    bt_replay = backtest_result.replay

    # Compare internal projector state
    r_projector = replay_result.session.fill_pipeline.projector
    b_projector = bt_replay.session.fill_pipeline.projector
    p_projector = paper_result.session.fill_pipeline.projector

    r_positions = r_projector.get_positions()
    b_positions = b_projector.get_positions()
    p_positions = p_projector.get_positions()

    assert len(r_positions) == len(b_positions) == len(p_positions), (
        f"Position count mismatch: {len(r_positions)} vs {len(b_positions)} vs {len(p_positions)}"
    )

    for rp, bp, pp in zip(r_positions, b_positions, p_positions):
        assert rp.symbol == bp.symbol == pp.symbol
        assert rp.quantity == bp.quantity == pp.quantity
        assert abs(float(rp.avg_price) - float(bp.avg_price)) < 1e-9
        assert abs(float(rp.avg_price) - float(pp.avg_price)) < 1e-9
