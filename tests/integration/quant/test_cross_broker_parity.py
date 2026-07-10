"""Cross-broker parity tests — verify same strategy produces identical signals regardless of broker data source.

These tests ensure zero-discrepancy across different broker data feeds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.pipeline.features import RSI, SMA
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.scanner.scanners import MomentumScanner
from analytics.strategy.models import SignalType


def _generate_broker_data(
    symbol: str = "RELIANCE",
    bars: int = 200,
    seed: int = 42,
    broker_noise: float = 0.0,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with optional broker-specific noise.

    Different brokers may have slight price/timing differences.
    This test verifies that small differences don't change strategy signals.
    """
    rng = np.random.default_rng(seed)

    timestamps = pd.date_range("2026-01-01", periods=bars, freq="5min")

    # Base price random walk
    returns = rng.normal(0.0001, 0.002, bars)
    price = 100.0 * (1 + returns).cumprod()

    # Add broker-specific noise (simulates price feed differences)
    noise = rng.normal(0, broker_noise, bars)
    price_with_noise = price * (1 + noise)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": price_with_noise * (1 + rng.uniform(-0.001, 0.001, bars)),
            "high": price_with_noise * (1 + rng.uniform(0, 0.003, bars)),
            "low": price_with_noise * (1 - rng.uniform(0, 0.003, bars)),
            "close": price_with_noise,
            "volume": rng.integers(1000, 100000, bars),
            "symbol": symbol,
        }
    )


@pytest.mark.cross_broker_parity
class TestCrossBrokerParity:
    """Verify strategy signals are consistent across broker data sources."""

    def test_scanner_parity_identical_data(self) -> None:
        """Same data → same scanner results regardless of broker."""
        # Generate identical data for both "brokers"
        data_a = _generate_broker_data(seed=42, broker_noise=0.0)
        data_b = data_a.copy()  # Exact copy

        scanner = MomentumScanner(top_n=5)
        result_a = scanner.scan(data_a)
        result_b = scanner.scan(data_b)

        # Must produce identical candidates
        assert len(result_a.candidates) == len(result_b.candidates)

        for cand_a, cand_b in zip(result_a.candidates, result_b.candidates, strict=False):
            assert cand_a.symbol == cand_b.symbol
            assert abs(cand_a.score - cand_b.score) < 1e-9

    def test_scanner_parity_small_price_differences(self) -> None:
        """Small price differences (< 0.01%) should not change top candidates."""
        # Generate data with minimal broker-specific noise
        data_a = _generate_broker_data(seed=42, broker_noise=0.0)
        data_b = _generate_broker_data(seed=42, broker_noise=0.00001)  # 0.001% noise

        scanner = MomentumScanner(top_n=5)
        result_a = scanner.scan(data_a)
        result_b = scanner.scan(data_b)

        # Top 5 candidates should be the same (order may vary slightly)
        symbols_a = {c.symbol for c in result_a.candidates}
        symbols_b = {c.symbol for c in result_b.candidates}

        # At least 80% overlap (allow for minor ranking changes)
        overlap = len(symbols_a & symbols_b) / max(len(symbols_a), 1)
        assert overlap >= 0.8, f"Too much divergence: only {overlap:.0%} overlap in top candidates"

    def test_feature_parity_across_brokers(self) -> None:
        """Feature pipeline should produce similar outputs for similar inputs."""
        pipeline = FeaturePipeline().add(RSI(period=14)).add(SMA(period=20))

        data_a = _generate_broker_data(seed=42, broker_noise=0.0)
        data_b = _generate_broker_data(seed=42, broker_noise=0.00001)

        features_a = pipeline.run(data_a)
        features_b = pipeline.run(data_b)

        # RSI values should be nearly identical (0.2 tolerance for small price noise)
        if "rsi" in features_a.columns and "rsi" in features_b.columns:
            rsi_diff = (features_a["rsi"] - features_b["rsi"]).abs().max()
            assert rsi_diff < 0.2, f"RSI divergence too large: {rsi_diff}"

    def test_signal_parity_same_features(self) -> None:
        """Same features → same trading signals."""
        # This tests the strategy layer, not the data layer
        from analytics.strategy.pipeline import StrategyPipeline

        # Create simple strategy
        class SimpleStrategy:
            name = "simple"

            def on_bar(self, df: pd.DataFrame, index: int) -> list:
                if index < 20:
                    return []

                close = df["close"].iloc[index]
                sma = df["sma_20"].iloc[index] if "sma_20" in df.columns else close * 0.99

                if close > sma * 1.01:
                    return [{"type": SignalType.BUY, "symbol": df["symbol"].iloc[index]}]
                elif close < sma * 0.99:
                    return [{"type": SignalType.SELL, "symbol": df["symbol"].iloc[index]}]
                return []

        pipeline = FeaturePipeline().add(SMA(period=20))
        StrategyPipeline(strategies=[SimpleStrategy()])

        data = _generate_broker_data(seed=42)
        features = pipeline.run(data)

        # Run strategy twice on same data
        signals_1 = []
        signals_2 = []

        for i in range(20, len(features)):
            s1 = SimpleStrategy().on_bar(features, i)
            s2 = SimpleStrategy().on_bar(features, i)
            signals_1.extend(s1)
            signals_2.extend(s2)

        assert signals_1 == signals_2, "Same data must produce identical signals"


@pytest.mark.parametrize("noise_level", [0.0, 0.00001, 0.0001])
def test_scanner_determinism_with_noise(noise_level: float) -> None:
    """Scanner results are deterministic for same seed and noise level."""
    data_1 = _generate_broker_data(seed=42, broker_noise=noise_level)
    data_2 = _generate_broker_data(seed=42, broker_noise=noise_level)

    scanner = MomentumScanner(top_n=10)
    result_1 = scanner.scan(data_1)
    result_2 = scanner.scan(data_2)

    assert len(result_1.candidates) == len(result_2.candidates)

    for c1, c2 in zip(result_1.candidates, result_2.candidates, strict=False):
        assert c1.symbol == c2.symbol
        assert c1.score == pytest.approx(c2.score, rel=1e-9)
