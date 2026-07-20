"""Tests for the standalone StatisticsEngine (Tier 2-E).

Two kinds of tests:
    1. Per-metric tests on hand-built fixtures with known answers (exact /
       approx assertions).
    2. Parity tests proving the extracted engine yields the same numbers as
       ``BacktestResult`` when fed the exact input the backtest used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.backtest.engine import ResearchMode
from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
from analytics.replay.models import SimulatedTrade
from domain.analytics.statistics import StatisticsEngine, TradeStatistics

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trending_data() -> pd.DataFrame:
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    up = np.cumsum(np.abs(np.random.randn(100)) * 1.5) + 100
    down = up[-1] - np.cumsum(np.abs(np.random.randn(100)) * 1.2)
    close = np.concatenate([up, down])
    volume = np.random.randint(200000, 800000, n).astype(float)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - np.random.rand(n),
            "high": close + np.random.rand(n) * 3,
            "low": close - np.random.rand(n) * 3,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def benchmark_data() -> pd.DataFrame:
    np.random.seed(99)
    n = 200
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 20000 + np.cumsum(np.random.randn(n) * 50)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - 10,
            "high": close + 20,
            "low": close - 20,
            "close": close,
            "volume": np.random.randint(1000000, 5000000, n).astype(float),
        }
    )


@pytest.fixture
def pipeline() -> FeaturePipeline:
    return FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))


def _make_trade(pnl, pnl_pct, strategy="Momentum", entry=None, exit=None):
    return SimulatedTrade(
        symbol="X",
        side="BUY",
        entry_price=100,
        exit_price=100 + pnl / 100,
        quantity=100,
        pnl=pnl,
        pnl_pct=pnl_pct,
        strategy=strategy,
        entry_time=entry,
        exit_time=exit,
    )


# ---------------------------------------------------------------------------
# Per-metric known-answer tests
# ---------------------------------------------------------------------------


class TestTotalReturn:
    def test_known_answer(self) -> None:
        total, pct = StatisticsEngine.total_return(100.0, 110.0)
        assert total == pytest.approx(10.0)
        assert pct == pytest.approx(0.1)

    def test_zero_initial(self) -> None:
        total, pct = StatisticsEngine.total_return(0.0, 110.0)
        assert total == pytest.approx(110.0)
        assert pct == 0.0


class TestCAGR:
    def test_one_year(self) -> None:
        # 252 bars == 1 year at annualization_factor 252.
        cagr = StatisticsEngine.cagr(100.0, 110.0, 252, 252)
        assert cagr == pytest.approx(0.1)

    def test_too_few_periods(self) -> None:
        assert StatisticsEngine.cagr(100.0, 110.0, 1, 252) == 0.0


class TestRiskMetrics:
    def test_volatility(self) -> None:
        returns = np.array([0.01, -0.02, 0.03, 0.0, -0.01])
        expected = float(np.std(returns) * np.sqrt(252))
        assert StatisticsEngine.volatility(returns, 252) == pytest.approx(expected)

    def test_sharpe(self) -> None:
        returns = np.array([0.01, -0.02, 0.03, 0.0, -0.01])
        rf = 0.065
        excess = returns - rf / 252
        expected = float(np.mean(excess) / np.std(excess) * np.sqrt(252))
        assert StatisticsEngine.sharpe(returns, 252, rf) == pytest.approx(expected)

    def test_sortino(self) -> None:
        returns = np.array([0.01, -0.02, 0.03, 0.0, -0.01])
        rf = 0.065
        excess = returns - rf / 252
        downside = returns[returns < 0]
        expected = float(np.mean(excess) / np.std(downside) * np.sqrt(252))
        assert StatisticsEngine.sortino(returns, 252, rf) == pytest.approx(expected)

    def test_max_drawdown_and_duration(self) -> None:
        equities = [100.0, 110.0, 90.0, 80.0]
        dd, duration = StatisticsEngine.max_drawdown(equities)
        # peak=110 at idx1; trough=80 at idx3 -> dd=0.2727.., duration=2
        assert dd == pytest.approx(30.0 / 110.0, rel=1e-9)
        assert duration == 2

    def test_calmar(self) -> None:
        assert StatisticsEngine.calmar(0.2, 0.1) == pytest.approx(2.0)
        assert StatisticsEngine.calmar(0.2, 0.0) == 0.0


class TestAnalyzeTrades:
    def test_empty(self) -> None:
        stats = StatisticsEngine.analyze_trades([])
        assert isinstance(stats, TradeStatistics)
        assert stats.total_trades == 0
        assert stats.win_rate == 0.0
        assert stats.profit_factor == 0.0

    def test_known_answer_int_pnl(self) -> None:
        trades = [
            _make_trade(1000, 10.0),
            _make_trade(-500, -5.0),
            _make_trade(1500, 15.0, strategy="Breakout"),
        ]
        stats = StatisticsEngine.analyze_trades(trades)
        assert stats.total_trades == 3
        assert stats.winning_trades == 2
        assert stats.losing_trades == 1
        assert stats.win_rate == pytest.approx(2 / 3)
        assert stats.avg_win == pytest.approx(1250.0)
        assert stats.avg_loss == pytest.approx(-500.0)
        assert stats.profit_factor == pytest.approx(2500 / 500)
        assert stats.largest_win == 1500.0
        assert stats.largest_loss == -500.0
        assert stats.trades_by_strategy == {"Momentum": 2, "Breakout": 1}

    def test_decimal_pnl_preserves_profit_factor_type(self) -> None:
        from decimal import Decimal

        trades = [
            _make_trade(Decimal("1000"), 10.0),
            _make_trade(Decimal("-500"), -5.0),
        ]
        stats = StatisticsEngine.analyze_trades(trades)
        # Mirrors backtest real runs where pnl is a Decimal.
        assert stats.profit_factor == Decimal("2")

    def test_consecutive_and_expectancy(self) -> None:
        # W L W W L  -> max 2 wins, max 2 losses
        trades = [
            _make_trade(100, 1.0),
            _make_trade(-50, -1.0),
            _make_trade(100, 1.0),
            _make_trade(100, 1.0),
            _make_trade(-50, -1.0),
        ]
        stats = StatisticsEngine.analyze_trades(trades)
        assert stats.max_consecutive_wins == 2
        # The two losses are separated by two wins -> max consecutive losses = 1.
        assert stats.max_consecutive_losses == 1
        # EV = 0.6*100 + 0.4*(-50) = 40
        assert stats.expected_value == pytest.approx(40.0)

    def test_holding_period(self) -> None:
        from datetime import datetime

        e1 = datetime(2026, 1, 1)
        x1 = datetime(2026, 1, 3)  # 2 days
        trades = [_make_trade(100, 1.0, entry=e1, exit=x1)]
        stats = StatisticsEngine.analyze_trades(trades)
        assert stats.avg_holding_bars == pytest.approx(2.0)


class TestBenchmarkMetrics:
    def test_known_answer(self) -> None:
        # equity curve -> strat returns [0.0, 0.1]
        equity_curve = [(pd.Timestamp("2026-01-01"), 100.0), (pd.Timestamp("2026-01-02"), 100.0), (pd.Timestamp("2026-01-03"), 110.0)]
        bench = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=3, freq="D"),
                "close": [100.0, 100.0, 120.0],
            }
        )
        out = StatisticsEngine.benchmark_metrics(
            equity_curve, bench, risk_free_rate=0.0, annualization_factor=252
        )
        # beta = cov/var(bench) = 0.01/0.02 = 0.5
        assert out["beta"] == pytest.approx(0.5)
        # alpha = mean(strat) - beta*mean(bench) = 0.05 - 0.5*0.1 = 0.0
        assert out["alpha"] == pytest.approx(0.0)
        # IR = (0.05 - 0.1)/std([0,-0.1]); np.std ddof=0 -> std=0.05 -> -1.0
        assert out["information_ratio"] == pytest.approx(-1.0, rel=1e-9)

    def test_empty_or_missing_columns(self) -> None:
        equity_curve = [(pd.Timestamp("2026-01-01"), 100.0)]
        assert StatisticsEngine.benchmark_metrics(equity_curve, pd.DataFrame(), risk_free_rate=0.0, annualization_factor=252) == {}
        no_close = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=2, freq="D")})
        assert StatisticsEngine.benchmark_metrics(equity_curve, no_close, risk_free_rate=0.0, annualization_factor=252) == {}


# ---------------------------------------------------------------------------
# Parity: extracted engine == BacktestResult
# ---------------------------------------------------------------------------


class TestParityWithBacktest:
    def test_metrics_match_backtest_no_benchmark(
        self, trending_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20), mode=ResearchMode.PURE_SIM)
        result = engine.run(trending_data, symbol="TEST")

        session = result.replay.session
        initial = session.equity_curve[0][1]
        final = session.current_equity
        computed = StatisticsEngine.compute(
            session.equity_curve,
            session.trades,
            initial=initial,
            final=final,
            annualization_factor=engine._config.annualization_factor,
            risk_free_rate=engine._config.risk_free_rate,
        )

        m = result.metrics
        assert computed["total_return"] == pytest.approx(m.total_return)
        assert computed["total_return_pct"] == pytest.approx(m.total_return_pct)
        assert computed["cagr"] == pytest.approx(m.cagr)
        assert computed["volatility"] == pytest.approx(m.volatility)
        assert computed["sharpe_ratio"] == pytest.approx(m.sharpe_ratio)
        assert computed["sortino_ratio"] == pytest.approx(m.sortino_ratio)
        assert computed["max_drawdown"] == pytest.approx(m.max_drawdown)
        assert computed["max_drawdown_duration"] == m.max_drawdown_duration
        assert computed["calmar_ratio"] == pytest.approx(m.calmar_ratio)

        ta = m.trade_analysis
        stats = computed["trade_analysis"]
        assert stats.total_trades == ta.total_trades
        assert stats.win_rate == pytest.approx(ta.win_rate)
        assert stats.profit_factor == ta.profit_factor
        assert stats.avg_win == pytest.approx(ta.avg_win)
        assert stats.avg_loss == pytest.approx(ta.avg_loss)
        assert stats.max_consecutive_wins == ta.max_consecutive_wins
        assert stats.trades_by_strategy == ta.trades_by_strategy

    def test_metrics_match_backtest_with_benchmark(
        self, trending_data: pd.DataFrame, benchmark_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20), mode=ResearchMode.PURE_SIM)
        result = engine.run(trending_data, symbol="TEST", benchmark=benchmark_data)

        session = result.replay.session
        initial = session.equity_curve[0][1]
        final = session.current_equity
        computed = StatisticsEngine.compute(
            session.equity_curve,
            session.trades,
            initial=initial,
            final=final,
            annualization_factor=engine._config.annualization_factor,
            risk_free_rate=engine._config.risk_free_rate,
            benchmark=benchmark_data,
        )

        m = result.metrics
        assert computed["alpha"] == pytest.approx(m.alpha)
        assert computed["beta"] == pytest.approx(m.beta)
        assert computed["benchmark_return"] == pytest.approx(m.benchmark_return)
        assert computed["tracking_error"] == pytest.approx(m.tracking_error)
        assert computed["information_ratio"] == pytest.approx(m.information_ratio)

    def test_replay_engine_uses_same_engine(
        self, trending_data: pd.DataFrame, pipeline: FeaturePipeline
    ) -> None:
        """ReplayEngine.compute_statistics must agree with BacktestEngine output."""
        bench_engine = BacktestEngine(pipeline, config=BacktestConfig(warmup_bars=20), mode=ResearchMode.PURE_SIM)
        result = bench_engine.run(trending_data, symbol="TEST")

        from analytics.replay import ReplayEngine

        replay_engine = ReplayEngine(
            pipeline, config=bench_engine._config, allow_simulate_without_oms=True
        )
        replay_result = replay_engine.run(trending_data, symbol="TEST")
        replay_stats = replay_engine.compute_statistics(replay_result.session)

        m = result.metrics
        assert replay_stats["sharpe_ratio"] == pytest.approx(m.sharpe_ratio)
        assert replay_stats["max_drawdown"] == pytest.approx(m.max_drawdown)
        assert replay_stats["trade_analysis"].total_trades == m.trade_analysis.total_trades
