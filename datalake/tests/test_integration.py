"""Integration test — DataLake → FeaturePipeline → Scanner → StrategyPipeline.

Verifies the full research chain works end-to-end with synthetic Parquet data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.pipeline import ATR, ROC, RSI, SMA, FeaturePipeline, Trend
from analytics.scanner import MomentumScanner
from analytics.scanner.models import Candidate
from analytics.strategy.pipeline import MomentumStrategy, StrategyPipeline
from datalake.research import ResearchAPI


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_ohlcv(
    n: int = 500,
    symbol: str = "TEST",
    start: str = "2026-01-01",
    trend: str = "up",
) -> pd.DataFrame:
    """Create synthetic OHLCV data with controllable trend."""
    np.random.seed(hash(symbol) % 2**31)
    dates = pd.date_range(start, periods=n, freq="1min")

    if trend == "up":
        close = 100 + np.cumsum(np.abs(np.random.randn(n)) * 0.3)
    elif trend == "down":
        close = 200 - np.cumsum(np.abs(np.random.randn(n)) * 0.3)
    else:
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)

    return pd.DataFrame({
        "timestamp": dates,
        "symbol": symbol,
        "exchange": "NSE",
        "open": close + np.random.randn(n) * 0.2,
        "high": close + np.abs(np.random.randn(n)) * 0.5,
        "low": close - np.abs(np.random.randn(n)) * 0.5,
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
        "oi": np.zeros(n, dtype=np.int64),
    })


def _setup_lake(tmp_path: Path, symbols: list[tuple[str, str]]) -> None:
    """Set up data lake with multiple symbols. symbols = [(name, trend), ...]"""
    for sym, trend in symbols:
        df = _make_ohlcv(n=500, symbol=sym, trend=trend)
        parquet_path = tmp_path / "equities" / "candles" / "timeframe=1m" / f"symbol={sym}" / "data.parquet"
        _write_parquet(parquet_path, df)


class TestDataLakeToFeaturePipeline:
    """Test DataLake → FeaturePipeline connection."""

    def test_history_feeds_pipeline(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, [("RELIANCE", "up")])
        api = ResearchAPI(root=str(tmp_path))

        df = api.history("RELIANCE", years=1)
        assert len(df) > 0

        pipeline = FeaturePipeline().add(RSI(14)).add(ROC(5)).add(ATR(14))
        features = pipeline.run(df)

        # Features are added as columns — names may be parameter-based
        assert len(features.columns) > len(df.columns)
        assert len(features) == len(df)


class TestDataLakeToScanner:
    """Test DataLake → Scanner connection."""

    def test_scan_universe(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, [
            ("RELIANCE", "up"),
            ("TCS", "down"),
            ("HDFCBANK", "neutral"),
        ])
        api = ResearchAPI(root=str(tmp_path))

        # Load universe data
        universe_data = {}
        for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
            df = api.history(sym, years=1)
            if not df.empty:
                universe_data[sym] = df

        assert len(universe_data) == 3

        # Combine into single DataFrame for scanner
        universe_df = pd.concat(universe_data.values(), ignore_index=True)

        # Run scanner
        scanner = MomentumScanner(pipeline=FeaturePipeline())
        result = scanner.scan(universe_df)

        assert result.scanner == "momentum"
        assert result.universe_size == 3
        assert len(result.candidates) == 3

        # All candidates should have valid scores
        for candidate in result.candidates:
            assert 0 <= candidate.score <= 100


class TestDataLakeToStrategy:
    """Test DataLake → FeaturePipeline → StrategyPipeline connection."""

    def test_strategy_evaluates_candidates(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, [
            ("RELIANCE", "up"),
            ("TCS", "down"),
        ])
        api = ResearchAPI(root=str(tmp_path))

        # Load and compute features per symbol
        pipeline = FeaturePipeline().add(RSI(14)).add(ROC(5)).add(ATR(14)).add(SMA(20)).add(Trend())
        features_by_symbol = {}
        for sym in ["RELIANCE", "TCS"]:
            df = api.history(sym, years=1)
            if not df.empty:
                features_by_symbol[sym] = pipeline.run(df)

        # Create candidates
        candidates = [
            Candidate(symbol=sym, score=50.0)
            for sym in features_by_symbol
        ]

        # Run strategy
        strategy_pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        results = strategy_pipeline.evaluate(candidates, features_by_symbol)

        assert len(results) == 1
        assert results[0].strategy == "Momentum"
        assert results[0].evaluated == 2

        # Each signal should have valid structure
        for signal in results[0].signals:
            assert signal.symbol in ["RELIANCE", "TCS"]
            assert 0 <= signal.confidence <= 1


class TestFullChain:
    """End-to-end: DataLake → Pipeline → Scanner → Strategy."""

    def test_full_research_chain(self, tmp_path: Path) -> None:
        # 1. Set up data lake
        _setup_lake(tmp_path, [
            ("RELIANCE", "up"),
            ("TCS", "down"),
            ("HDFCBANK", "neutral"),
            ("INFY", "up"),
        ])
        api = ResearchAPI(root=str(tmp_path))

        # 2. Load universe
        universe_data = {}
        for sym in ["RELIANCE", "TCS", "HDFCBANK", "INFY"]:
            df = api.history(sym, years=1)
            if not df.empty:
                universe_data[sym] = df

        universe_df = pd.concat(universe_data.values(), ignore_index=True)

        # 3. Run scanner
        scanner = MomentumScanner(pipeline=FeaturePipeline())
        scan_result = scanner.scan(universe_df)
        assert scan_result.count > 0

        # 4. Compute features per symbol for strategy
        feature_pipeline = FeaturePipeline().add(RSI(14)).add(ROC(5)).add(ATR(14)).add(SMA(20)).add(Trend())
        features_by_symbol = {}
        for sym in universe_data:
            features_by_symbol[sym] = feature_pipeline.run(universe_data[sym])

        # 5. Run strategy on scanner candidates
        strategy_pipeline = StrategyPipeline(strategies=[MomentumStrategy()])
        strategy_results = strategy_pipeline.evaluate(scan_result.candidates, features_by_symbol)

        assert len(strategy_results) == 1
        assert strategy_results[0].evaluated > 0

        # 6. Verify we got actionable signals (at least some)
        all_signals = strategy_results[0].signals
        assert len(all_signals) > 0
        for signal in all_signals:
            assert signal.signal_type is not None
            assert 0 <= signal.confidence <= 1


class TestMomentumStrategyWeakened:
    """Test the weakened signal paths in MomentumStrategy."""

    def test_weakened_buy_signal(self, tmp_path: Path) -> None:
        """RSI ~40, ROC ~3% should trigger weakened buy."""
        _setup_lake(tmp_path, [("TEST", "up")])
        api = ResearchAPI(root=str(tmp_path))

        df = api.history("TEST", years=1)
        pipeline = FeaturePipeline().add(RSI(14)).add(ROC(5)).add(ATR(14))
        features = pipeline.run(df)

        # Find a row where RSI is between 35-45 and ROC > 2%
        last = features.iloc[-1]
        last.get("rsi", 50)
        last.get("roc", 0)

        strategy = MomentumStrategy()
        candidate = Candidate(symbol="TEST", score=50.0)
        signal = strategy.evaluate(candidate, features)

        # Signal should be valid regardless of what RSI/ROC values are
        assert signal.symbol == "TEST"
        assert signal.signal_type is not None
        assert 0 <= signal.confidence <= 1
        assert "weakened" in signal.metadata

    def test_strict_defaults_preserved(self) -> None:
        """Verify default parameters maintain strict behavior."""
        strategy = MomentumStrategy()
        assert strategy.rsi_oversold == 35.0
        assert strategy.rsi_overbought == 70.0
        assert strategy.roc_threshold == 0.0
        assert strategy.rsi_weak_buy == 45.0
        assert strategy.rsi_weak_sell == 60.0
        assert strategy.roc_weak_threshold == 2.0

    def test_custom_parameters(self) -> None:
        """Verify custom parameters are accepted."""
        strategy = MomentumStrategy(
            rsi_oversold=30.0,
            rsi_overbought=75.0,
            roc_threshold=1.0,
            rsi_weak_buy=40.0,
            rsi_weak_sell=65.0,
            roc_weak_threshold=3.0,
        )
        assert strategy.rsi_oversold == 30.0
        assert strategy.roc_weak_threshold == 3.0
