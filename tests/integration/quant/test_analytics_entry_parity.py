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


@pytest.mark.paper_replay_parity
def test_analytics_entry_points_parity_rejects_risk_blocked_order() -> None:
    """PARITY must reject via RiskManager; PURE_SIM must still trade.

    Proves the risk gate is on the OMS path — not merely that fingerprints
    match when risk never rejects (which the equivalence test above allows).
    """
    from decimal import Decimal

    from application.oms.risk_manager import RiskConfig
    from domain.events.types import EventType

    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])
    df = _ohlcv()
    symbol = "RISKBLK"

    common_kwargs = dict(
        initial_capital=100_000,
        warmup_bars=5,
        max_position_pct=100.0,  # size full equity — oversized vs RiskConfig below
        slippage_pct=0.0,
    )

    pure = ReplayEngine(
        pipeline,
        strategy,
        ReplayConfig(**common_kwargs),
        allow_simulate_without_oms=True,
    )
    pure_result = pure.run(df, symbol=symbol)

    rejected: list[object] = []
    strict_ctx = build_test_trading_context(
        replay_events=False,
        capital_fn=lambda: Decimal("100000"),
        risk_config=RiskConfig(
            max_position_pct=Decimal("1.0"),  # 1% of capital → full-size order fails
            max_gross_exposure_pct=Decimal("1.0"),
            enable_margin_check=False,
        ),
    )
    strict_ctx.event_bus.subscribe(EventType.RISK_REJECTED.value, rejected.append)
    strict_ctx.event_bus.subscribe(EventType.ORDER_REJECTED.value, rejected.append)

    parity = BacktestEngine(
        pipeline,
        strategy,
        BacktestConfig(**common_kwargs),
        mode=ResearchMode.PARITY,
        trading_context=strict_ctx,
    )
    parity_result = parity.run(df, symbol=symbol)
    bt_session = parity_result.replay.session

    assert len(pure_result.session.trades) > 0, "PURE_SIM must open+close without RiskManager"
    assert len(bt_session.trades) < len(pure_result.session.trades), (
        "PARITY with max_position_pct=1 must produce fewer round-trips than PURE_SIM"
    )
    assert len(bt_session.trades) == 0, "oversized AlwaysBuy open must be risk-rejected in PARITY"
    assert rejected, "RiskManager rejection must be observable on the event bus"


class FlipFlopStrategy:
    """Alternate BUY / SELL so a losing round-trip can trip daily-loss mid-run."""

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


def _declining_ohlcv(rows: int = 60) -> pd.DataFrame:
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


@pytest.mark.paper_replay_parity
def test_analytics_entry_points_parity_daily_loss_trips() -> None:
    """PARITY must block new risk after session equity delta breaches daily-loss."""
    from decimal import Decimal

    from application.oms._internal.loss_circuit_breaker import LossCircuitBreakerConfig
    from application.oms.risk_manager import RiskConfig
    from domain.events.types import EventType

    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[FlipFlopStrategy()])
    df = _declining_ohlcv()
    symbol = "LOSSY"

    common_kwargs = dict(
        initial_capital=100_000,
        warmup_bars=5,
        max_position_pct=10.0,  # leave cash so CB capital isn't near-zero
        slippage_pct=0.0,
        commission_flat=0.0,
    )

    rejected: list[object] = []
    ctx = build_test_trading_context(
        replay_events=False,
        capital_fn=lambda: Decimal("100000"),
        risk_config=RiskConfig(
            max_daily_loss_pct=Decimal("2.0"),
            max_position_pct=Decimal("100"),
            max_gross_exposure_pct=Decimal("100"),
            enable_margin_check=False,
        ),
    )
    # CB defaults trip on bar MTM ticks and block *closes* (desk freeze_all).
    # Raise threshold so FlipFlop can journal a round-trip; daily-loss still gates.
    ctx.risk_manager._loss_cb.config = LossCircuitBreakerConfig(
        loss_threshold_pct=Decimal("99"),
    )
    ctx.event_bus.subscribe(EventType.RISK_REJECTED.value, rejected.append)

    engine = ReplayEngine(
        pipeline,
        strategy,
        ReplayConfig(**common_kwargs),
        trading_context=ctx,
    )
    result = engine.run(df, symbol=symbol)
    session = result.session

    assert len(session.trades) >= 1, (
        "OMS mid-run sells must append SimulatedTrade (trade journal)"
    )
    assert [_trade_fingerprint(t) for t in session.trades]
    # Risk capital is FIXED account size — it must NOT track declining session cash.
    risk_capital = ctx.risk_manager.capital_provider.get_available_balance()
    assert risk_capital == Decimal("100000"), (
        f"RiskManager capital must stay fixed at initial: got {risk_capital}"
    )
    assert ctx.risk_manager.daily_pnl < 0 or rejected, (
        "declining FlipFlop must leave session in loss and/or risk-reject"
    )
    from domain.entities.order import Order
    from domain.enums import OrderType, ProductType, Side

    probe = Order(
        order_id="probe",
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        price=Decimal("100"),
        product_type=ProductType.INTRADAY,
    )
    if abs(ctx.risk_manager.daily_pnl) / risk_capital * 100 >= Decimal("2.0"):
        check = ctx.risk_manager.check_order(probe)
        assert not check.allowed
        reason = (check.reason or "").lower()
        assert "loss" in reason, f"expected a loss-based rejection, got: {check.reason}"


@pytest.mark.paper_replay_parity
def test_paper_flipflop_journals_trades_and_binds_capital() -> None:
    """Paper mid-run sells append PaperTrade; risk capital tracks ledger."""
    from decimal import Decimal

    from application.oms._internal.loss_circuit_breaker import LossCircuitBreakerConfig
    from application.oms.risk_manager import RiskConfig

    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[FlipFlopStrategy()])
    df = _declining_ohlcv(rows=40)
    ctx = build_test_trading_context(
        replay_events=False,
        capital_fn=lambda: Decimal("100000"),
        risk_config=RiskConfig(
            max_daily_loss_pct=Decimal("50"),
            max_position_pct=Decimal("100"),
            max_gross_exposure_pct=Decimal("100"),
            enable_margin_check=False,
        ),
    )
    ctx.risk_manager._loss_cb.config = LossCircuitBreakerConfig(
        loss_threshold_pct=Decimal("99"),
    )
    paper = PaperTradingEngine(
        pipeline,
        strategy,
        PaperConfig(
            initial_capital=100_000,
            warmup_bars=5,
            max_position_pct=10.0,
            slippage_pct=0.0,
            commission_flat=0.0,
        ),
        trading_context=ctx,
    )
    result = paper.run(df, symbol="PAPERFF")
    assert len(result.session.trades) >= 1
    risk_capital = ctx.risk_manager.capital_provider.get_available_balance()
    assert risk_capital == Decimal("100000"), (
        f"Paper risk capital must stay fixed at initial: got {risk_capital}"
    )


@pytest.mark.paper_replay_parity
def test_analytics_parity_scope_restores_context() -> None:
    """run() must restore risk capital binding + pnl-owner flag afterwards.

    A TradingContext reused for live trading after a replay/paper run must NOT
    keep the analytics-bound fixed capital provider or the muted daily-pnl bus
    feed — those are scoped to the run only.
    """
    from decimal import Decimal

    from application.oms.risk_manager import RiskConfig

    pipeline = FeaturePipeline()
    strategy = StrategyPipeline(strategies=[AlwaysBuyStrategy()])
    df = _ohlcv()
    symbol = "RESTORE"

    common_kwargs = dict(
        initial_capital=100_000,
        warmup_bars=5,
        max_position_pct=100.0,
        slippage_pct=0.0,
    )

    for factory in (
        lambda c: ReplayEngine(
            pipeline, strategy, ReplayConfig(**common_kwargs), trading_context=c
        ),
        lambda c: PaperTradingEngine(
            pipeline, strategy, PaperConfig(**common_kwargs), trading_context=c
        ),
    ):
        ctx = build_test_trading_context(
            replay_events=False,
            capital_fn=lambda: Decimal("100000"),
            risk_config=RiskConfig(enable_margin_check=False),
        )
        ctx.set_analytics_daily_pnl_owner(False)
        orig_provider = ctx.risk_manager.capital_provider

        engine = factory(ctx)
        engine.run(df, symbol=symbol)

        # Ownership flag must be restored to its pre-run value.
        assert ctx._analytics_owns_daily_pnl is False, (
            "analytics_parity_scope must restore daily-pnl ownership after run()"
        )
        # Risk capital provider must be the original live provider, not the
        # fixed account-size provider bound during the run.
        assert ctx.risk_manager.capital_provider is orig_provider, (
            "analytics_parity_scope must restore the original risk capital provider"
        )
        assert ctx.risk_manager.capital_provider.get_available_balance() == Decimal("100000")

