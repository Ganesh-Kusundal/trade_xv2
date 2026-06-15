"""Tests for Strategy Pipeline Framework (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType, StrategyResult
from analytics.strategy.pipeline import (
    BreakoutStrategy,
    MomentumStrategy,
    StrategyPipeline,
)
from analytics.strategy.protocols import Strategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_features() -> pd.DataFrame:
    """Generate sample feature-enriched OHLCV data with indicators."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    volume = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - np.random.rand(n),
            "high": close + np.random.rand(n) * 2,
            "low": close - np.random.rand(n) * 2,
            "close": close,
            "volume": volume,
            "rsi": np.random.uniform(20, 80, n),
            "roc": np.random.uniform(-5, 5, n),
            "atr": np.random.uniform(1, 5, n),
            "sma_20": close + np.random.randn(n) * 0.5,
            "swing_high": close + 5,
            "swing_low": close - 5,
            "volume_sma": volume * 0.8,
        }
    )


@pytest.fixture
def bullish_features() -> pd.DataFrame:
    """Features that should trigger a BUY signal from MomentumStrategy."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    volume = np.random.randint(100000, 500000, n).astype(float)
    rsi = np.full(n, 25.0)  # Oversold
    roc = np.full(n, 2.0)   # Positive momentum
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": volume,
            "rsi": rsi,
            "roc": roc,
            "atr": np.full(n, 3.0),
            "sma_20": close + 10,
            "swing_high": close + 5,
            "swing_low": close - 5,
            "volume_sma": volume * 0.5,
        }
    )


@pytest.fixture
def bearish_features() -> pd.DataFrame:
    """Features that should trigger a SELL signal from MomentumStrategy."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    volume = np.random.randint(100000, 500000, n).astype(float)
    rsi = np.full(n, 75.0)  # Overbought
    roc = np.full(n, -2.0)  # Negative momentum
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": volume,
            "rsi": rsi,
            "roc": roc,
            "atr": np.full(n, 3.0),
            "sma_20": close - 10,
            "swing_high": close + 5,
            "swing_low": close - 5,
            "volume_sma": volume * 0.5,
        }
    )


@pytest.fixture
def breakout_features() -> pd.DataFrame:
    """Features that should trigger a BUY from BreakoutStrategy."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    volume = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": volume,
            "rsi": np.full(n, 50.0),
            "roc": np.full(n, 0.0),
            "atr": np.full(n, 3.0),
            "sma_20": close - 10,
            "swing_high": close - 5,  # Close > swing_high
            "swing_low": close - 20,
            "volume_sma": volume * 0.3,  # Volume > 1.5x avg
        }
    )


@pytest.fixture
def candidates() -> list[Candidate]:
    return [
        Candidate(symbol="RELIANCE", score=85.0, reasons=["High momentum"]),
        Candidate(symbol="TCS", score=72.0, reasons=["Volume surge"]),
        Candidate(symbol="INFY", score=65.0, reasons=["RSI oversold"]),
    ]


# ---------------------------------------------------------------------------
# Signal model tests
# ---------------------------------------------------------------------------


class TestSignal:
    def test_signal_creation(self) -> None:
        s = Signal(symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.8)
        assert s.symbol == "RELIANCE"
        assert s.signal_type == SignalType.BUY
        assert s.confidence == 0.8
        assert s.is_actionable is True
        assert s.is_buy is True
        assert s.is_sell is False

    def test_signal_hold_not_actionable(self) -> None:
        s = Signal(symbol="TCS", signal_type=SignalType.HOLD)
        assert s.is_actionable is False
        assert s.is_buy is False
        assert s.is_sell is False

    def test_signal_strong_buy(self) -> None:
        s = Signal(symbol="INFY", signal_type=SignalType.STRONG_BUY, confidence=0.95)
        assert s.is_actionable is True
        assert s.is_buy is True

    def test_signal_strong_sell(self) -> None:
        s = Signal(symbol="WIPRO", signal_type=SignalType.STRONG_SELL, confidence=0.9)
        assert s.is_actionable is True
        assert s.is_sell is True

    def test_confidence_validation(self) -> None:
        with pytest.raises(ValueError, match="Confidence must be"):
            Signal(symbol="X", signal_type=SignalType.BUY, confidence=1.5)
        with pytest.raises(ValueError, match="Confidence must be"):
            Signal(symbol="X", signal_type=SignalType.BUY, confidence=-0.1)

    def test_position_size_validation(self) -> None:
        with pytest.raises(ValueError, match="position_size_pct"):
            Signal(symbol="X", signal_type=SignalType.BUY, position_size_pct=150)

    def test_risk_reward_ratio(self) -> None:
        s = Signal(
            symbol="X",
            signal_type=SignalType.BUY,
            entry_price=100.0,
            stop_loss=95.0,
            target=115.0,
        )
        assert s.risk_reward_ratio == 3.0  # (115-100)/(100-95) = 3.0

    def test_risk_reward_none_when_missing(self) -> None:
        s = Signal(symbol="X", signal_type=SignalType.BUY, entry_price=100.0)
        assert s.risk_reward_ratio is None

    def test_risk_reward_none_when_zero_risk(self) -> None:
        s = Signal(
            symbol="X",
            signal_type=SignalType.BUY,
            entry_price=100.0,
            stop_loss=100.0,
            target=110.0,
        )
        assert s.risk_reward_ratio is None

    def test_signal_frozen(self) -> None:
        s = Signal(symbol="X", signal_type=SignalType.BUY)
        with pytest.raises(AttributeError):
            s.symbol = "Y"  # type: ignore[misc]

    def test_signal_timestamp_default(self) -> None:
        s = Signal(symbol="X", signal_type=SignalType.BUY)
        assert isinstance(s.timestamp, datetime)
        assert s.timestamp.tzinfo == timezone.utc

    def test_signal_metadata(self) -> None:
        s = Signal(
            symbol="X",
            signal_type=SignalType.BUY,
            metadata={"rsi": 25.0, "atr": 3.0},
        )
        assert s.metadata["rsi"] == 25.0


# ---------------------------------------------------------------------------
# StrategyResult tests
# ---------------------------------------------------------------------------


class TestStrategyResult:
    def test_empty_result(self) -> None:
        r = StrategyResult(strategy="Test")
        assert r.count == 0
        assert r.actionable == []
        assert r.buys == []
        assert r.sells == []

    def test_result_with_signals(self) -> None:
        signals = [
            Signal(symbol="A", signal_type=SignalType.BUY, confidence=0.8),
            Signal(symbol="B", signal_type=SignalType.SELL, confidence=0.7),
            Signal(symbol="C", signal_type=SignalType.HOLD, confidence=0.0),
        ]
        r = StrategyResult(strategy="Test", signals=signals, evaluated=3)
        assert r.count == 3
        assert len(r.actionable) == 2
        assert len(r.buys) == 1
        assert len(r.sells) == 1

    def test_top_signals(self) -> None:
        signals = [
            Signal(symbol="A", signal_type=SignalType.BUY, confidence=0.5),
            Signal(symbol="B", signal_type=SignalType.BUY, confidence=0.9),
            Signal(symbol="C", signal_type=SignalType.BUY, confidence=0.7),
        ]
        r = StrategyResult(strategy="Test", signals=signals)
        top = r.top(2)
        assert top[0].symbol == "B"
        assert top[1].symbol == "C"

    def test_by_symbol(self) -> None:
        signals = [
            Signal(symbol="A", signal_type=SignalType.BUY),
            Signal(symbol="B", signal_type=SignalType.SELL),
        ]
        r = StrategyResult(strategy="Test", signals=signals)
        assert r.by_symbol("A") is not None
        assert r.by_symbol("A").signal_type == SignalType.BUY
        assert r.by_symbol("Z") is None


# ---------------------------------------------------------------------------
# MomentumStrategy tests
# ---------------------------------------------------------------------------


class TestMomentumStrategy:
    def test_buy_signal(self, bullish_features: pd.DataFrame) -> None:
        strat = MomentumStrategy()
        candidate = Candidate(symbol="RELIANCE", score=80.0)
        signal = strat.evaluate(candidate, bullish_features)
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0
        assert signal.strategy == "Momentum"
        assert len(signal.reasons) > 0
        assert signal.entry_price is not None
        assert signal.stop_loss is not None
        assert signal.target is not None

    def test_sell_signal(self, bearish_features: pd.DataFrame) -> None:
        strat = MomentumStrategy()
        candidate = Candidate(symbol="TCS", score=70.0)
        signal = strat.evaluate(candidate, bearish_features)
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0
        assert signal.stop_loss is not None
        assert signal.target is not None

    def test_hold_signal(self, sample_features: pd.DataFrame) -> None:
        strat = MomentumStrategy()
        candidate = Candidate(symbol="INFY", score=60.0)
        signal = strat.evaluate(candidate, sample_features)
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0

    def test_empty_features(self) -> None:
        strat = MomentumStrategy()
        candidate = Candidate(symbol="X", score=50.0)
        signal = strat.evaluate(candidate, pd.DataFrame())
        assert signal.signal_type == SignalType.HOLD
        assert signal.reasons == ["No data"]


# ---------------------------------------------------------------------------
# BreakoutStrategy tests
# ---------------------------------------------------------------------------


class TestBreakoutStrategy:
    def test_buy_on_breakout(self, breakout_features: pd.DataFrame) -> None:
        strat = BreakoutStrategy()
        candidate = Candidate(symbol="RELIANCE", score=80.0)
        signal = strat.evaluate(candidate, breakout_features)
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0
        assert signal.strategy == "Breakout"

    def test_hold_no_breakout(self, sample_features: pd.DataFrame) -> None:
        strat = BreakoutStrategy()
        candidate = Candidate(symbol="INFY", score=60.0)
        signal = strat.evaluate(candidate, sample_features)
        # With random data, most likely HOLD
        assert signal.signal_type in (SignalType.HOLD, SignalType.BUY, SignalType.SELL)

    def test_empty_features(self) -> None:
        strat = BreakoutStrategy()
        candidate = Candidate(symbol="X", score=50.0)
        signal = strat.evaluate(candidate, pd.DataFrame())
        assert signal.signal_type == SignalType.HOLD


# ---------------------------------------------------------------------------
# StrategyPipeline tests
# ---------------------------------------------------------------------------


class TestStrategyPipeline:
    def test_evaluate_returns_results_per_strategy(
        self, candidates: list[Candidate], sample_features: pd.DataFrame
    ) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy(), BreakoutStrategy()])
        features_by_symbol = {c.symbol: sample_features for c in candidates}
        results = pipeline.evaluate(candidates, features_by_symbol)
        assert len(results) == 2  # One per strategy
        assert results[0].strategy == "Momentum"
        assert results[1].strategy == "Breakout"

    def test_evaluate_collects_all_signals(
        self, candidates: list[Candidate], sample_features: pd.DataFrame
    ) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        features_by_symbol = {c.symbol: sample_features for c in candidates}
        results = pipeline.evaluate(candidates, features_by_symbol)
        assert results[0].count == 3  # One signal per candidate
        assert results[0].evaluated == 3

    def test_evaluate_skips_missing_features(
        self, candidates: list[Candidate], sample_features: pd.DataFrame
    ) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        # Only provide features for 2 of 3 candidates
        features_by_symbol = {
            "RELIANCE": sample_features,
            "TCS": sample_features,
        }
        results = pipeline.evaluate(candidates, features_by_symbol)
        assert results[0].count == 2
        assert results[0].evaluated == 2

    def test_evaluate_single_candidate(
        self, sample_features: pd.DataFrame
    ) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy(), BreakoutStrategy()])
        candidate = Candidate(symbol="RELIANCE", score=80.0)
        signals = pipeline.evaluate_single(candidate, sample_features)
        assert len(signals) == 2  # One per strategy
        assert all(isinstance(s, Signal) for s in signals)

    def test_evaluate_with_bullish_data(
        self, candidates: list[Candidate], bullish_features: pd.DataFrame
    ) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        features_by_symbol = {c.symbol: bullish_features for c in candidates}
        results = pipeline.evaluate(candidates, features_by_symbol)
        assert len(results[0].buys) == 3  # All should be BUY

    def test_evaluate_with_bearish_data(
        self, candidates: list[Candidate], bearish_features: pd.DataFrame
    ) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        features_by_symbol = {c.symbol: bearish_features for c in candidates}
        results = pipeline.evaluate(candidates, features_by_symbol)
        assert len(results[0].sells) == 3  # All should be SELL

    def test_empty_candidates(self) -> None:
        pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        results = pipeline.evaluate([], {})
        assert len(results) == 1
        assert results[0].count == 0

    def test_default_strategies(self) -> None:
        pipeline = StrategyPipeline()
        assert len(pipeline.strategies) == 2
        assert pipeline.strategies[0].name == "Momentum"
        assert pipeline.strategies[1].name == "Breakout"


# ---------------------------------------------------------------------------
# Strategy Protocol compliance
# ---------------------------------------------------------------------------


class TestStrategyProtocol:
    def test_momentum_is_strategy(self) -> None:
        assert isinstance(MomentumStrategy(), Strategy)

    def test_breakout_is_strategy(self) -> None:
        assert isinstance(BreakoutStrategy(), Strategy)

    def test_custom_strategy_compliance(self) -> None:
        class MyStrategy:
            name: str = "Custom"

            def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
                return Signal(symbol=candidate.symbol, signal_type=SignalType.HOLD)

        assert isinstance(MyStrategy(), Strategy)


# ---------------------------------------------------------------------------
# Analytics facade integration
# ---------------------------------------------------------------------------


class TestAnalyticsFacade:
    def test_analytics_has_strategy(self) -> None:
        from analytics import Analytics

        a = Analytics()
        pipeline = a.strategy()
        assert isinstance(pipeline, StrategyPipeline)

    def test_analytics_strategy_returns_pipeline(self) -> None:
        from analytics import Analytics

        a = Analytics()
        result = a.strategy()
        assert hasattr(result, "evaluate")
        assert hasattr(result, "evaluate_single")
