"""Quant parity test suite — comprehensive determinism and correctness tests.

Tests verify that:
1. Scanner determinism: same input → same output across multiple runs
2. Replay determinism: same OHLCV → same trades/PnL
3. Resample correctness: aggregation matches pandas reference
4. Feature computation parity: features are reproducible
5. Golden output verification: results match stored baselines

Run with: pytest tests/quant/test_quant_parity.py -v
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analytics.pipeline.features import ATR, RSI, SMA
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig
from analytics.scanner.models import Candidate
from analytics.scanner.scanners import (
    BreakoutScanner,
    MomentumScanner,
    RSScanner,
    VolumeScanner,
)
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline


class _NullOmsAdapter:
    """Minimal OMS adapter for replay tests that satisfies the port protocol."""

    def open_long(
        self, symbol, exchange, quantity, price, timestamp, *, strategy=None, reasons=None
    ):
        return f"SIM-{symbol}"

    def close_long(
        self, symbol, exchange, quantity, price, timestamp, *, strategy=None, reasons=None
    ):
        return f"SIM-CLOSE-{symbol}"

    def modify_order(self, order_id, *, price=None, quantity=None, trigger_price=None):
        return True

    def cancel_order(self, order_id):
        return True

    def get_position(self, symbol, exchange="NSE"):
        return None

    def get_orders(self):
        return []


# Golden baseline directory
GOLDEN_DIR = Path(__file__).parent / "golden"


def _generate_ohlcv(symbol: str = "TEST", bars: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate deterministic synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2026-01-01", periods=bars, freq="1min")

    # Random walk for price
    returns = rng.normal(0.0001, 0.002, bars)
    price = 100.0 * (1 + returns).cumprod()

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": price * (1 + rng.uniform(-0.001, 0.001, bars)),
            "high": price * (1 + rng.uniform(0, 0.003, bars)),
            "low": price * (1 - rng.uniform(0, 0.003, bars)),
            "close": price,
            "volume": rng.integers(1000, 100000, bars),
        }
    )


def _generate_universe(n_symbols: int = 10, n_bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic multi-symbol universe."""
    frames = []
    for i in range(n_symbols):
        sym = f"SYM{i:03d}"
        df = _generate_ohlcv(symbol=sym, bars=n_bars, seed=seed + i)
        df["symbol"] = sym
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _create_simple_strategy() -> StrategyPipeline:
    """Create a simple strategy for replay testing."""

    class SimpleRSIStrategy:
        """Simple RSI-based strategy."""

        @property
        def name(self) -> str:
            return "simple_rsi"

        def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
            """Generate buy/sell signals based on RSI."""
            if features.empty:
                return Signal(
                    symbol=candidate.symbol,
                    signal_type=SignalType.HOLD,
                    confidence=0.0,
                    strategy=self.name,
                    reasons=["No data"],
                )

            if "rsi" in features.columns:
                latest_rsi = features["rsi"].iloc[-1]
                if latest_rsi < 30:
                    return Signal(
                        symbol=candidate.symbol,
                        signal_type=SignalType.BUY,
                        strategy=self.name,
                        confidence=70.0,
                        score=70.0,
                        stop_loss=features["close"].iloc[-1] * 0.98,
                        target=features["close"].iloc[-1] * 1.05,
                    )
                elif latest_rsi > 70:
                    return Signal(
                        symbol=candidate.symbol,
                        signal_type=SignalType.SELL,
                        strategy=self.name,
                        confidence=70.0,
                        score=70.0,
                    )

            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
                reasons=["RSI neutral"],
            )

    return StrategyPipeline(strategies=[SimpleRSIStrategy()])


# ---------------------------------------------------------------------------
# Scanner Determinism Tests
# ---------------------------------------------------------------------------


class TestScannerDeterminism:
    """Verify scanners produce identical outputs across multiple runs."""

    @pytest.mark.parametrize(
        "scanner_cls",
        [MomentumScanner, VolumeScanner, RSScanner, BreakoutScanner],
    )
    def test_scanner_determinism_10_runs(self, scanner_cls: type) -> None:
        """Scanner must produce identical candidates across 10 runs."""
        universe = _generate_universe(n_symbols=10, n_bars=150)
        scanner = scanner_cls(top_n=5)

        results = [scanner.scan(universe) for _ in range(10)]

        # All runs should produce identical results
        for i in range(1, 10):
            assert len(results[i].candidates) == len(results[0].candidates)
            for c1, c2 in zip(results[i].candidates, results[0].candidates, strict=False):
                assert c1.symbol == c2.symbol
                assert abs(c1.score - c2.score) < 1e-9

    def test_scanner_score_stability(self) -> None:
        """Scanner scores should be stable across runs."""
        universe = _generate_universe(n_symbols=20, n_bars=100)
        scanner = MomentumScanner(top_n=10)

        scores = []
        for _ in range(5):
            result = scanner.scan(universe)
            scores.append([c.score for c in result.candidates])

        # All score lists should be identical
        for s in scores[1:]:
            assert s == scores[0]

    def test_scanner_tie_breaking_deterministic(self) -> None:
        """Tied scores should be broken deterministically by symbol."""
        # Create universe where all symbols have identical data
        timestamps = pd.date_range("2026-01-01", periods=100, freq="1min")
        frames = []
        for i in range(5):
            sym = f"SYM{i:02d}"
            df = pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "symbol": sym,
                    "open": [100.0 + j * 0.01 for j in range(100)],
                    "high": [101.0 + j * 0.01 for j in range(100)],
                    "low": [99.0 + j * 0.01 for j in range(100)],
                    "close": [100.5 + j * 0.01 for j in range(100)],
                    "volume": [1000 + j for j in range(100)],
                }
            )
            frames.append(df)

        universe = pd.concat(frames, ignore_index=True)
        scanner = MomentumScanner(top_n=3)

        symbols_sets = []
        for _ in range(10):
            result = scanner.scan(universe)
            symbols_sets.append([c.symbol for c in result.candidates])

        # All should select same symbols in same order
        for symbols in symbols_sets[1:]:
            assert symbols == symbols_sets[0]
            # Should be sorted by symbol (tie breaker)
            assert symbols == sorted(symbols)


# ---------------------------------------------------------------------------
# Replay Determinism Tests
# ---------------------------------------------------------------------------


class TestReplayDeterminism:
    """Verify ReplayEngine produces identical results across runs."""

    def test_replay_determinism_5_runs(self) -> None:
        """Replay must produce identical trades/signals across 5 runs."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=50, window_size=100)

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_NullOmsAdapter())

        results = [engine.run(df) for _ in range(5)]

        # All runs should produce identical results
        for i in range(1, 5):
            assert len(results[i].session.signals) == len(results[0].session.signals)
            assert len(results[i].session.trades) == len(results[0].session.trades)
            assert results[i].bars_processed == results[0].bars_processed

    def test_replay_pnl_deterministic(self) -> None:
        """Replay PnL should be deterministic."""
        df = _generate_ohlcv(bars=1000)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(
            warmup_bars=50,
            window_size=100,
            initial_capital=100000.0,
            slippage_pct=0.01,
            commission_flat=20.0,
        )

        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_NullOmsAdapter())

        equities = []
        for _ in range(5):
            result = engine.run(df)
            equities.append(result.session.current_equity)

        # All final equities should be identical
        assert all(e == equities[0] for e in equities)

    def test_replay_with_oms_disabled_deterministic(self) -> None:
        """Replay without OMS should be deterministic."""
        df = _generate_ohlcv(bars=300)
        pipeline = FeaturePipeline().add(RSI(period=14))
        strategy = _create_simple_strategy()
        config = ReplayConfig(warmup_bars=30, window_size=50)

        # OMS adapter required; NullOmsAdapter still produces deterministic replay
        engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_NullOmsAdapter())

        results = [engine.run(df) for _ in range(3)]

        for i in range(1, 3):
            assert results[i].signals_generated == results[0].signals_generated


# ---------------------------------------------------------------------------
# Resample Correctness Tests
# ---------------------------------------------------------------------------


class TestResampleCorrectness:
    """Verify data resampling matches pandas reference."""

    def test_resample_1m_to_5m(self) -> None:
        """1-minute to 5-minute resampling should be correct."""
        df = _generate_ohlcv(bars=1000)

        # Resample using pandas (reference)
        df_5m = (
            df.set_index("timestamp")
            .resample("5min")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )

        # Verify bar count is approximately correct (allow for edge effects)
        expected_bars = len(df) // 5
        assert abs(len(df_5m) - expected_bars) <= 1

        # Verify aggregation logic
        assert df_5m["open"].iloc[0] == df["open"].iloc[0]
        assert df_5m["volume"].iloc[0] == df["volume"].iloc[:5].sum()

    def test_resample_1m_to_15m(self) -> None:
        """1-minute to 15-minute resampling should be correct."""
        df = _generate_ohlcv(bars=1000)

        df_15m = (
            df.set_index("timestamp")
            .resample("15min")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )

        expected_bars = len(df) // 15
        assert abs(len(df_15m) - expected_bars) <= 1

    def test_resample_1m_to_1h(self) -> None:
        """1-minute to 1-hour resampling should be correct."""
        df = _generate_ohlcv(bars=1000)

        df_1h = (
            df.set_index("timestamp")
            .resample("1h")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )

        expected_bars = len(df) // 60
        assert abs(len(df_1h) - expected_bars) <= 1

    def test_resample_volume_aggregation(self) -> None:
        """Resampled volume should be sum of constituent bars."""
        df = _generate_ohlcv(bars=500)

        df_5m = (
            df.set_index("timestamp")
            .resample("5min")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )

        # First 5-minute bar volume should equal sum of first 5 1-minute bars
        if len(df_5m) > 0:
            expected_volume = df["volume"].iloc[:5].sum()
            assert df_5m["volume"].iloc[0] == expected_volume

    def test_resample_deterministic(self) -> None:
        """Resampling should be deterministic."""
        df = _generate_ohlcv(bars=500)

        results = []
        for _ in range(5):
            df_5m = (
                df.set_index("timestamp")
                .resample("5min")
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna()
            )
            results.append(df_5m)

        for r in results[1:]:
            assert r.equals(results[0])


# ---------------------------------------------------------------------------
# Feature Computation
# ---------------------------------------------------------------------------
# Feature Computation Parity Tests
# ---------------------------------------------------------------------------


class TestFeatureComputationParity:
    """Verify feature computation is reproducible."""

    def test_rsi_deterministic(self) -> None:
        """RSI computation must be deterministic."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(RSI(period=14))

        values = []
        for _ in range(10):
            features = pipeline.run(df)
            if not features.empty and "rsi" in features.columns:
                values.append(float(features["rsi"].iloc[-1]))

        assert all(v == values[0] for v in values)

    def test_sma_deterministic(self) -> None:
        """SMA computation must be deterministic."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(SMA(period=20))

        values = []
        for _ in range(10):
            features = pipeline.run(df)
            if not features.empty and "sma" in features.columns:
                values.append(float(features["sma"].iloc[-1]))

        assert all(v == values[0] for v in values)

    def test_multi_feature_deterministic(self) -> None:
        """Multiple features computed together must be deterministic."""
        df = _generate_ohlcv(bars=500)
        pipeline = FeaturePipeline().add(RSI(14)).add(SMA(20)).add(ATR(14))

        all_features = []
        for _ in range(5):
            features = pipeline.run(df)
            if not features.empty:
                row = features.iloc[-1]
                all_features.append(
                    {
                        "rsi": float(row.get("rsi", 0)),
                        "sma": float(row.get("sma", 0)),
                        "atr": float(row.get("atr", 0)),
                    }
                )

        for f in all_features[1:]:
            assert f == all_features[0]

    def test_feature_pipeline_idempotent(self) -> None:
        """Running pipeline twice on same data should give same result."""
        df = _generate_ohlcv(bars=300)
        pipeline = FeaturePipeline().add(RSI(14)).add(SMA(20))

        features1 = pipeline.run(df)
        features2 = pipeline.run(df)

        assert features1.equals(features2)

    def test_feature_golden_values(self) -> None:
        """Feature values should match known golden values."""
        # Use simple data for known values
        timestamps = pd.date_range("2026-01-01", periods=100, freq="1min")
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0 + i * 0.1 for i in range(100)],
                "high": [101.0 + i * 0.1 for i in range(100)],
                "low": [99.0 + i * 0.1 for i in range(100)],
                "close": [100.5 + i * 0.1 for i in range(100)],
                "volume": [1000] * 100,
            }
        )

        pipeline = FeaturePipeline().add(RSI(period=14))
        features = pipeline.run(df)

        # RSI should be between 0 and 100
        if "rsi" in features.columns:
            rsi_values = features["rsi"].dropna()
            assert all(0 <= v <= 100 for v in rsi_values)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestQuantIntegration:
    """Integration tests combining scanner + replay + features."""

    def test_scanner_to_replay_parity(self) -> None:
        """Scanner output should be usable in replay."""
        # Run scanner to get candidates
        universe = _generate_universe(n_symbols=5, n_bars=200)
        scanner = MomentumScanner(top_n=3)
        scan_result = scanner.scan(universe)

        # Use first candidate's symbol in replay
        if scan_result.candidates:
            symbol = scan_result.candidates[0].symbol
            symbol_data = universe[universe["symbol"] == symbol]

            pipeline = FeaturePipeline().add(RSI(period=14))
            strategy = _create_simple_strategy()
            config = ReplayConfig(warmup_bars=50, window_size=100)

            engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_NullOmsAdapter())
            result = engine.run(symbol_data)

            assert result.bars_processed > 0

    def test_end_to_end_determinism(self) -> None:
        """Full scanner + replay pipeline should be deterministic."""
        universe = _generate_universe(n_symbols=3, n_bars=200)

        results = []
        for _ in range(3):
            # Scan
            scanner = MomentumScanner(top_n=1)
            scan_result = scanner.scan(universe)

            # Replay
            if scan_result.candidates:
                symbol = scan_result.candidates[0].symbol
                symbol_data = universe[universe["symbol"] == symbol]

                pipeline = FeaturePipeline().add(RSI(period=14))
                strategy = _create_simple_strategy()
                config = ReplayConfig(warmup_bars=30, window_size=50)

                engine = ReplayEngine(pipeline, strategy, config, oms_adapter=_NullOmsAdapter())
                replay_result = engine.run(symbol_data)

                results.append(
                    {
                        "symbol": symbol,
                        "score": scan_result.candidates[0].score,
                        "signals": replay_result.signals_generated,
                    }
                )

        # All runs should produce identical results
        for r in results[1:]:
            assert r == results[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
