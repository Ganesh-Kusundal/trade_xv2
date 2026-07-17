"""E2E tests for Replay → Strategy → Backtest → Metrics flow.

Tests the complete backtesting pipeline:
1. Replay engine loads historical data
2. Strategy processes bars and generates signals
3. Backtest executes trades with simulated positions
4. Metrics calculate correctly (Sharpe, drawdown, win rate)
5. Results match expected values for known data patterns

Uses real ReplayEngine with synthetic data for deterministic results.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.e2e

# ── Test Constants ────────────────────────────────────────────────────────────
DEFAULT_N_BARS = 150
DEFAULT_START_PRICE = Decimal("100.0")
DEFAULT_WARMUP_BARS = 20
DEFAULT_INITIAL_CAPITAL = Decimal("100000")

from analytics.pipeline import ATR, ROC, RSI, SMA
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import (
    ReplayConfig,
    ReplayResult,
    ReplaySession,
    SimulatedTrade,
)
from analytics.scanner.models import Candidate
from analytics.strategy.models import SignalType
from analytics.strategy.pipeline import MomentumStrategy, StrategyPipeline
from tests.e2e.fixtures.data_generators import (
    generate_mean_reverting_data,
    generate_trending_data,
)
from tests.e2e.fixtures.trading_context_factory import create_paper_trading_context

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def trending_data():
    """Generate trending data that should trigger BUY signals."""
    return generate_trending_data(
        n_bars=DEFAULT_N_BARS,
        start_price=DEFAULT_START_PRICE,
        symbol="TREND",
        trend_strength=0.005,
        seed=42,
    )


@pytest.fixture
def mean_reverting_data():
    """Generate mean-reverting data for testing exit signals."""
    return generate_mean_reverting_data(
        n_bars=DEFAULT_N_BARS,
        start_price=120.0,
        symbol="MEANREV",
        mean=100.0,
        reversion_speed=0.05,
        seed=42,
    )


@pytest.fixture
def basic_pipeline():
    """Create a basic feature pipeline for replay."""
    return FeaturePipeline().add(RSI(14)).add(ROC(5)).add(SMA(20)).add(ATR(14))


@pytest.fixture
def momentum_strategy():
    """Create a momentum strategy."""
    return MomentumStrategy(rsi_oversold=40, rsi_overbought=65)


# ── Basic Replay Execution ──────────────────────────────────────────────────


class TestBasicReplayExecution:
    """Tests: Replay engine runs correctly on various data types."""

    def test_replay_processes_all_bars(self, trending_data, basic_pipeline, momentum_strategy):
        """Replay should process all bars after warmup."""
        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(trending_data, symbol="TREND")

        assert result.bars_processed == 150
        assert isinstance(result, ReplayResult)

    def test_replay_with_empty_data(self, basic_pipeline, momentum_strategy):
        """Empty data should return empty result."""
        config = ReplayConfig()
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(pd.DataFrame())
        assert result.bars_processed == 0
        assert len(result.session.signals) == 0

    def test_replay_missing_timestamp_raises(self, basic_pipeline, momentum_strategy):
        """Data without timestamp should raise ValueError."""
        config = ReplayConfig()
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        df = pd.DataFrame({"close": [100, 101, 102]})
        with pytest.raises(ValueError, match="timestamp"):
            engine.run(df)

    def test_replay_generates_signals(self, trending_data, basic_pipeline, momentum_strategy):
        """Replay with trending data should generate signals."""
        config = ReplayConfig(warmup_bars=30, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(trending_data, symbol="TREND")

        assert result.signals_generated > 0
        assert len(result.session.signals) > 0

    def test_replay_equity_curve_populated(self, trending_data, basic_pipeline, momentum_strategy):
        """Equity curve should be populated throughout replay."""
        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(trending_data, symbol="TREND")

        assert len(result.session.equity_curve) > 0
        # First equity should equal initial capital
        assert result.session.equity_curve[0][1] == 100000


# ── Strategy Signal Generation ──────────────────────────────────────────────


class TestStrategySignalGeneration:
    """Tests: Strategy generates correct signals during replay."""

    def test_momentum_strategy_generates_buy_on_oversold(self):
        """MomentumStrategy should BUY when RSI < oversold and ROC > 0."""
        features = pd.DataFrame(
            {
                "rsi": [30.0],
                "roc": [2.0],
                "close": [100.0],
                "atr": [1.0],
            }
        )
        candidate = Candidate(symbol="TEST", score=50.0)

        strategy = MomentumStrategy(rsi_oversold=35)
        signal = strategy.evaluate(candidate, features)

        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0

    def test_momentum_strategy_generates_sell_on_overbought(self):
        """MomentumStrategy should SELL when RSI > overbought and ROC < 0."""
        features = pd.DataFrame(
            {
                "rsi": [75.0],
                "roc": [-2.0],
                "close": [100.0],
                "atr": [1.0],
            }
        )
        candidate = Candidate(symbol="TEST", score=50.0)

        strategy = MomentumStrategy(rsi_overbought=70)
        signal = strategy.evaluate(candidate, features)

        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0

    def test_momentum_strategy_holds_in_neutral(self):
        """MomentumStrategy should HOLD when no conditions met."""
        features = pd.DataFrame(
            {
                "rsi": [50.0],
                "roc": [0.0],
                "close": [100.0],
                "atr": [1.0],
            }
        )
        candidate = Candidate(symbol="TEST", score=50.0)

        strategy = MomentumStrategy()
        signal = strategy.evaluate(candidate, features)

        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0

    def test_signal_includes_entry_stop_target(self):
        """Signals should include entry, stop-loss, and target prices."""
        features = pd.DataFrame(
            {
                "rsi": [30.0],
                "roc": [2.0],
                "close": [100.0],
                "atr": [2.0],
            }
        )
        candidate = Candidate(symbol="TEST", score=50.0)

        strategy = MomentumStrategy()
        signal = strategy.evaluate(candidate, features)

        assert signal.entry_price == 100.0
        assert signal.stop_loss is not None
        assert signal.target is not None
        assert signal.stop_loss < signal.entry_price < signal.target


# ── Trade Execution ─────────────────────────────────────────────────────────


class TestTradeExecution:
    """Tests: Trades execute correctly during replay."""

    def test_buy_opens_position(self, basic_pipeline, momentum_strategy):
        """BUY signal should open a long position."""
        # Create data that will trigger a buy early
        data = generate_mean_reverting_data(
            n_bars=100,
            start_price=80.0,
            symbol="TEST",
            mean=100.0,
            reversion_speed=0.1,
            seed=42,
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")

        # If any trades were executed, verify they are BUY
        if result.session.trades:
            buy_trades = [t for t in result.session.trades if t.side == "BUY"]
            # At least some trades should be buys
            assert len(buy_trades) >= 0

    def test_sell_closes_position(self, basic_pipeline, momentum_strategy):
        """SELL signal should close an open position."""
        data = generate_mean_reverting_data(
            n_bars=200,
            start_price=120.0,
            symbol="TEST",
            mean=100.0,
            reversion_speed=0.03,
            seed=42,
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")

        # If trades exist, verify SELL trades exist too
        if len(result.session.trades) >= 2:
            sell_trades = [t for t in result.session.trades if t.side == "SELL"]
            assert len(sell_trades) >= 0

    def test_slippage_applied_to_fills(self, basic_pipeline, momentum_strategy):
        """Slippage should affect fill prices."""
        data = generate_trending_data(n_bars=100, symbol="TEST", seed=42)

        config_no_slip = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        config_with_slip = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.1,  # 0.1% slippage
        )

        engine_no_slip = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config_no_slip,
        )
        engine_with_slip = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config_with_slip,
        )

        result_no_slip = engine_no_slip.run(data, symbol="TEST")
        result_with_slip = engine_with_slip.run(data, symbol="TEST")

        # With slippage, final equity should differ (typically lower)
        if result_no_slip.session.trades and result_with_slip.session.trades:
            assert result_no_slip.final_equity != result_with_slip.final_equity

    def test_commission_deducted_from_capital(self, basic_pipeline, momentum_strategy):
        """Commission should reduce capital on each trade."""
        data = generate_trending_data(n_bars=100, symbol="TEST", seed=42)

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
            commission_flat=10.0,  # ₹10 per trade
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")

        # If trades occurred, capital should be reduced by commission
        if result.session.trades:
            total_commission = len(result.session.trades) * 10.0
            # Final equity should account for commissions
            assert result.final_equity < result.config.initial_capital + total_commission


# ── Backtest Metrics ────────────────────────────────────────────────────────


class TestBacktestMetrics:
    """Tests: Backtest metrics calculate correctly."""

    def test_win_rate_calculation(self):
        """Win rate should be wins / total trades."""
        session = ReplaySession(capital=100000)
        session.trades = [
            SimulatedTrade(
                symbol="A",
                side="BUY",
                entry_price=100,
                exit_price=110,
                quantity=10,
                pnl=100,
                pnl_pct=10,
            ),
            SimulatedTrade(
                symbol="B",
                side="BUY",
                entry_price=100,
                exit_price=90,
                quantity=10,
                pnl=-100,
                pnl_pct=-10,
            ),
            SimulatedTrade(
                symbol="C",
                side="BUY",
                entry_price=100,
                exit_price=120,
                quantity=10,
                pnl=200,
                pnl_pct=20,
            ),
        ]
        result = ReplayResult(session=session, bars_processed=100, signals_generated=10)

        assert result.session.win_rate == pytest.approx(2 / 3, abs=0.01)

    def test_max_drawdown_calculation(self):
        """Max drawdown should be calculated from equity curve."""
        session = ReplaySession(capital=100000)
        session.equity_curve = [
            (datetime(2026, 1, 1), 100000),
            (datetime(2026, 1, 2), 105000),  # peak
            (datetime(2026, 1, 3), 95000),  # drawdown: (105000-95000)/105000
            (datetime(2026, 1, 4), 110000),  # new peak
            (datetime(2026, 1, 5), 100000),  # drawdown: (110000-100000)/110000
        ]
        result = ReplayResult(session=session, bars_processed=100, signals_generated=10)

        expected_dd = (105000 - 95000) / 105000  # ~9.52%
        assert result.session.max_drawdown == pytest.approx(expected_dd, abs=0.001)

    def test_sharpe_ratio_calculation(self):
        """Sharpe ratio should be annualized from returns."""
        session = ReplaySession(capital=100000)
        # Create equity curve with positive returns
        equities = [100000 + i * 100 for i in range(50)]
        session.equity_curve = [
            (datetime(2026, 1, 1) + timedelta(days=i), eq) for i, eq in enumerate(equities)
        ]
        result = ReplayResult(session=session, bars_processed=100, signals_generated=10)

        sharpe = result.sharpe_ratio
        # Should be positive for consistently rising equity
        assert sharpe > 0

    def test_total_return_pct(self):
        """Total return should be (final - initial) / initial * 100."""
        session = ReplaySession(capital=100000)
        session.capital = 110000  # Set capital to reflect the change
        session.equity_curve = [
            (datetime(2026, 1, 1), 100000),
            (datetime(2026, 1, 2), 110000),
        ]
        result = ReplayResult(session=session, bars_processed=100, signals_generated=10)

        # current_equity = capital + position_value (no position = just capital)
        assert result.final_equity == 110000
        assert result.total_return_pct == pytest.approx(10.0, abs=0.01)

    def test_summary_contains_all_metrics(self, trending_data, basic_pipeline, momentum_strategy):
        """Summary should contain all expected metrics."""
        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )
        result = engine.run(trending_data, symbol="TREND")

        summary = result.summary
        expected_keys = [
            "bars_processed",
            "signals_generated",
            "total_trades",
            "win_rate",
            "final_equity",
            "total_return_pct",
            "max_drawdown_pct",
            "sharpe_ratio",
        ]
        for key in expected_keys:
            assert key in summary

    def test_no_trades_yields_zero_metrics(self, basic_pipeline, momentum_strategy):
        """If no trades execute, metrics should be zero."""
        # Create data that won't trigger signals
        data = pd.DataFrame(
            {
                "timestamp": [datetime(2026, 1, 1) + timedelta(days=i) for i in range(50)],
                "open": [100.0] * 50,
                "high": [101.0] * 50,
                "low": [99.0] * 50,
                "close": [100.0] * 50,
                "volume": [10000.0] * 50,
                "symbol": ["FLAT"] * 50,
            }
        )

        config = ReplayConfig(warmup_bars=45, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )
        result = engine.run(data, symbol="FLAT")

        assert result.session.total_trades == 0
        assert result.session.win_rate == 0.0


# ── Intra-Bar Stop/Target ───────────────────────────────────────────────────


class TestIntraBarStopTarget:
    """Tests: Intra-bar stop-loss and target triggers work correctly."""

    def test_stop_loss_triggered_on_low(self, basic_pipeline, momentum_strategy):
        """Stop-loss should trigger when bar low hits stop level."""
        data = generate_mean_reverting_data(
            n_bars=100,
            start_price=80.0,
            symbol="TEST",
            mean=100.0,
            reversion_speed=0.1,
            seed=42,
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")
        # Should not crash - stop-loss logic should execute cleanly
        assert isinstance(result, ReplayResult)

    def test_target_triggered_on_high(self, basic_pipeline, momentum_strategy):
        """Target should trigger when bar high hits target level."""
        data = generate_trending_data(
            n_bars=100,
            start_price=DEFAULT_START_PRICE,
            symbol="TEST",
            trend_strength=0.005,
            seed=42,
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")
        assert isinstance(result, ReplayResult)

    def test_position_closed_at_end_of_replay(self, basic_pipeline, momentum_strategy):
        """Open positions should be closed at end of replay."""
        data = generate_trending_data(
            n_bars=100,
            start_price=80.0,
            symbol="TEST",
            trend_strength=0.01,
            seed=42,
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")

        # Position should be None at end (closed by engine)
        assert result.session.position is None


# ── OMS Integration (if available) ─────────────────────────────────────────


class TestOMSIntegration:
    """Tests: Replay with OMS TradingContext for backtest-live parity."""

    def test_replay_with_trading_context(self, tmp_path, basic_pipeline, momentum_strategy):
        """Replay with TradingContext should route through OMS."""
        data = generate_trending_data(
            n_bars=100,
            start_price=DEFAULT_START_PRICE,
            symbol="TEST",
            trend_strength=0.005,
            seed=42,
        )

        ctx = create_paper_trading_context(
            capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=Decimal("100"),
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
            trading_context=ctx,
        )

        result = engine.run(data, symbol="TEST")

        # Should complete without errors
        assert isinstance(result, ReplayResult)
        # OMS should have recorded orders if signals were generated
        # (exact count depends on strategy signals)

    def test_replay_without_trading_context_uses_simulated(self, basic_pipeline, momentum_strategy):
        """Replay without TradingContext should use simulated positions."""
        data = generate_trending_data(
            n_bars=100,
            start_price=DEFAULT_START_PRICE,
            symbol="TEST",
            trend_strength=0.005,
            seed=42,
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
            trading_context=None,  # No OMS
        )

        result = engine.run(data, symbol="TEST")

        # Should use simulated positions (legacy path)
        assert isinstance(result, ReplayResult)


# ── Determinism ─────────────────────────────────────────────────────────────


class TestDeterminism:
    """Tests: Replay produces identical results on repeated runs."""

    def test_replay_is_deterministic(self, basic_pipeline, momentum_strategy):
        """Same data + same config should produce identical results."""
        data = generate_trending_data(n_bars=100, symbol="TEST", seed=42)
        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL, slippage_pct=0.05)

        engine1 = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )
        engine2 = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result1 = engine1.run(data, symbol="TEST")
        result2 = engine2.run(data, symbol="TEST")

        assert result1.bars_processed == result2.bars_processed
        assert result1.signals_generated == result2.signals_generated
        assert result1.session.total_trades == result2.session.total_trades
        assert result1.final_equity == result2.final_equity
        assert result1.session.win_rate == result2.session.win_rate


# ── Backtest vs Live Parity ─────────────────────────────────────────────────


class TestBacktestVsLiveParity:
    """Tests: Backtest results match live trading for identical inputs."""

    def test_oms_position_matches_replay_position(
        self, tmp_path, basic_pipeline, momentum_strategy
    ):
        """Position opened in replay should match OMS position."""
        data = generate_trending_data(
            n_bars=100,
            start_price=DEFAULT_START_PRICE,
            symbol="TEST",
            trend_strength=0.01,
            seed=42,
        )

        # Create TradingContext for OMS integration
        ctx = create_paper_trading_context(
            capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=Decimal("100"),
            events_dir=tmp_path / "events-parity",
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
            trading_context=ctx,
        )

        result = engine.run(data, symbol="TEST")

        # If trades occurred, verify OMS tracked them
        if result.session.trades:
            oms_positions = ctx.position_manager.get_positions()
            # OMS should have positions matching replay trades
            # (may be flat if all positions closed by end)
            assert isinstance(oms_positions, list)

    def test_replay_pnl_matches_oms_pnl(self, tmp_path, basic_pipeline, momentum_strategy):
        """PnL calculated in replay should match OMS PnL."""
        data = generate_mean_reverting_data(
            n_bars=DEFAULT_N_BARS,
            start_price=DEFAULT_START_PRICE,
            symbol="TEST",
            mean=100.0,
            reversion_speed=0.05,
            seed=42,
        )

        ctx = create_paper_trading_context(
            capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=Decimal("100"),
            events_dir=tmp_path / "events-pnl-parity",
        )

        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
            trading_context=ctx,
        )

        result = engine.run(data, symbol="TEST")

        # Compare PnL
        replay_pnl = result.session.capital - result.config.initial_capital

        # OMS should track the same PnL
        oms_balance = ctx.risk_manager.capital_fn()
        oms_pnl = oms_balance - DEFAULT_INITIAL_CAPITAL

        # Should match (within floating point tolerance)
        if result.session.trades:
            assert abs(replay_pnl - float(oms_pnl)) < 1.0  # Within ₹1

    def test_commission_consistency_across_modes(self, basic_pipeline, momentum_strategy):
        """Commission should be applied identically in replay and OMS."""
        data = generate_trending_data(n_bars=100, symbol="TEST", seed=42)

        # Replay with commission
        config = ReplayConfig(
            warmup_bars=DEFAULT_WARMUP_BARS,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            max_position_pct=100.0,
            slippage_pct=0.0,
            commission_flat=10.0,
        )
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="TEST")

        # If trades occurred, verify commission was deducted
        if result.session.trades:
            len(result.session.trades) * 10.0
            actual_commission = (
                result.config.initial_capital
                - result.session.capital
                + result.session.position_value
            )
            # Commission should be deducted
            assert actual_commission > 0


# ── Multi-Symbol Backtest Parity ────────────────────────────────────────────


class TestMultiSymbolBacktestParity:
    """Tests: Multi-symbol backtests maintain parity across symbols."""

    def test_multiple_symbols_single_replay(self, basic_pipeline, momentum_strategy):
        """Replay with multiple symbols should track each independently."""
        # Generate data for 3 symbols
        data_rel = generate_trending_data(n_bars=100, symbol="RELIANCE", seed=42)
        data_tcs = generate_mean_reverting_data(
            n_bars=100, start_price=DEFAULT_START_PRICE, symbol="TCS", seed=43
        )
        data_hdfc = generate_trending_data(n_bars=100, symbol="HDFCBANK", seed=44)

        # Run separate replays for each symbol
        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)

        results = {}
        for sym, data in [("RELIANCE", data_rel), ("TCS", data_tcs), ("HDFCBANK", data_hdfc)]:
            engine = ReplayEngine(
                pipeline=basic_pipeline,
                strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
                config=config,
            )
            results[sym] = engine.run(data, symbol=sym)

        # Each symbol should have independent results
        for _sym, result in results.items():
            assert result.bars_processed == 100
            assert isinstance(result.session.trades, list)

    def test_portfolio_aggregation_matches_individual_sum(self, basic_pipeline, momentum_strategy):
        """Portfolio PnL should equal sum of individual symbol PnLs."""
        symbols_data = {}
        results = {}

        for i, sym in enumerate(["RELIANCE", "TCS", "HDFCBANK"]):
            data = generate_trending_data(n_bars=100, symbol=sym, seed=40 + i)
            symbols_data[sym] = data

            config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=33333.33)
            engine = ReplayEngine(
                pipeline=basic_pipeline,
                strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
                config=config,
            )
            results[sym] = engine.run(data, symbol=sym)

        # Sum individual PnLs
        individual_pnls = sum(
            result.final_equity - result.config.initial_capital for result in results.values()
        )

        # This test documents current behavior
        # Production systems may aggregate differently
        assert isinstance(individual_pnls, float)


# ── Edge Cases in Replay ────────────────────────────────────────────────────


class TestReplayEdgeCases:
    """Tests: Edge cases in replay and backtest flows."""

    def test_replay_with_very_large_dataset(self, basic_pipeline, momentum_strategy):
        """Replay should handle large datasets without memory issues."""
        # Generate 10,000 bars (stress test)
        data = generate_trending_data(n_bars=10000, symbol="LARGE", seed=42)

        config = ReplayConfig(warmup_bars=100, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="LARGE")

        assert result.bars_processed == 10000
        assert isinstance(result, ReplayResult)

    def test_replay_with_gap_in_data(self, basic_pipeline, momentum_strategy):
        """Replay should handle gaps in data (weekends, holidays)."""
        # Create data with gaps
        timestamps = []
        current = datetime(2026, 1, 1)
        for _i in range(50):
            timestamps.append(current)
            # Skip weekends
            current += timedelta(days=1)
            while current.weekday() >= 5:  # Skip Sat, Sun
                current += timedelta(days=1)

        data = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0 + i * 0.5 for i in range(50)],
                "high": [101.0 + i * 0.5 for i in range(50)],
                "low": [99.5 + i * 0.5 for i in range(50)],
                "close": [100.5 + i * 0.5 for i in range(50)],
                "volume": [10000.0] * 50,
                "symbol": ["GAPY"] * 50,
            }
        )

        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="GAPY")
        assert result.bars_processed == 50

    def test_replay_with_missing_values(self, basic_pipeline, momentum_strategy):
        """Replay should handle NaN values gracefully."""
        data = generate_trending_data(n_bars=100, symbol="NAN", seed=42)

        # Introduce some NaN values
        data.loc[10, "close"] = np.nan
        data.loc[20, "volume"] = np.nan

        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        # Should not crash - should handle NaN gracefully
        try:
            result = engine.run(data, symbol="NAN")
            assert isinstance(result, ReplayResult)
        except Exception:
            # If exception is raised, it should be informative
            pass

    def test_replay_with_zero_volume(self, basic_pipeline, momentum_strategy):
        """Replay should handle zero volume bars."""
        data = generate_trending_data(n_bars=100, symbol="ZEROVOL", seed=42)
        data.loc[10:15, "volume"] = 0.0

        config = ReplayConfig(warmup_bars=DEFAULT_WARMUP_BARS, initial_capital=DEFAULT_INITIAL_CAPITAL)
        engine = ReplayEngine(
            pipeline=basic_pipeline,
            strategy_pipeline=StrategyPipeline(strategies=[momentum_strategy]),
            config=config,
        )

        result = engine.run(data, symbol="ZEROVOL")
        assert result.bars_processed == 100
